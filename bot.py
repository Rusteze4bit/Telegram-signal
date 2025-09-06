import time
import requests
import json
import websocket
import threading
from datetime import datetime, timedelta
import statistics

# Telegram bot credentials
TOKEN = "8256982239:AAFZLRbcmRVgO1SiWOBqU7Hf00z6VU6nB64"
GROUP_ID = -1002810133474
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Deriv API WebSocket endpoint
DERIV_API_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

# Markets to analyze
MARKETS = ["R_10", "R_25", "R_50", "R_75", "R_100"]

# Market symbol to name mapping
MARKET_NAMES = {
    "R_10": "Volatility 10 Index",
    "R_25": "Volatility 25 Index",
    "R_50": "Volatility 50 Index",
    "R_75": "Volatility 75 Index",
    "R_100": "Volatility 100 Index",
}

# Store last 200 ticks for analysis
market_ticks = {market: [] for market in MARKETS}

# Track message IDs
active_messages = []
last_expired_id = None


def send_telegram_message(message: str, image_path="logo.png", keep=False):
    """Send a message with logo and Run button."""
    keyboard = {
        "inline_keyboard": [[
            {"text": "🚀 Run on KashyTrader", "url": "https://www.kashytrader.site/"}
        ]]
    }

    with open(image_path, "rb") as img:
        resp = requests.post(
            f"{BASE_URL}/sendPhoto",
            data={
                "chat_id": GROUP_ID,
                "caption": message,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(keyboard),
            },
            files={"photo": img}
        )

    if resp.ok:
        msg_id = resp.json()["result"]["message_id"]
        if not keep:
            active_messages.append(msg_id)
        return msg_id
    return None


def delete_messages():
    """Delete pre+main messages from last cycle."""
    global active_messages
    for msg_id in active_messages:
        requests.post(f"{BASE_URL}/deleteMessage", data={
            "chat_id": GROUP_ID,
            "message_id": msg_id
        })
    active_messages = []


def delete_last_expired():
    """Delete last expired message before sending a new cycle."""
    global last_expired_id
    if last_expired_id:
        requests.post(f"{BASE_URL}/deleteMessage", data={
            "chat_id": GROUP_ID,
            "message_id": last_expired_id
        })
        last_expired_id = None


def analyze_market(market: str, ticks: list):
    """
    Advanced adaptive analysis:
      - Dynamic window size (depends on volatility)
      - Ratio & streak analysis
      - Transition probability modeling
      - Adaptive confidence thresholds
      - Supports Under 6 and Under 8
    """
    if len(ticks) < 50:
        return None

    last_digits = [int(str(t)[-1]) for t in ticks]

    # --- Dynamic window size ---
    base_window = 50
    vol = statistics.pstdev(last_digits[-50:]) or 1
    window = int(base_window * (1 + vol / 10))
    window = min(window, len(last_digits))  # cap window
    digits = last_digits[-window:]

    # --- Basic ratios ---
    under6_ratio = sum(d < 6 for d in digits) / len(digits)
    under8_ratio = sum(d < 8 for d in digits) / len(digits)

    # --- Streak detection (last 10 digits) ---
    last10 = digits[-10:]
    streak_under6 = sum(d < 6 for d in last10) / 10
    streak_under8 = sum(d < 8 for d in last10) / 10

    # --- Transition probabilities ---
    trans_under6, trans_under8 = 0, 0
    for i in range(len(digits) - 1):
        if digits[i] < 6 and digits[i+1] < 6:
            trans_under6 += 1
        if digits[i] < 8 and digits[i+1] < 8:
            trans_under8 += 1
    trans_under6 /= max(1, len(digits) - 1)
    trans_under8 /= max(1, len(digits) - 1)

    # --- Weighted scoring system ---
    score_under6 = (
        under6_ratio * 0.4 +
        streak_under6 * 0.3 +
        trans_under6 * 0.2 +
        (1 / vol) * 0.1
    )

    score_under8 = (
        under8_ratio * 0.4 +
        streak_under8 * 0.3 +
        trans_under8 * 0.2 +
        (1 / vol) * 0.1
    )

    strength = {
        "Under 6": score_under6,
        "Under 8": score_under8
    }

    best_signal = max(strength, key=strength.get)
    confidence = strength[best_signal]

    # --- Adaptive confidence threshold ---
    if confidence < 0.55:
        return None  # skip weak signals

    return best_signal, confidence


def fetch_and_analyze():
    """Pick the best market and send full signal cycle."""
    global last_expired_id

    # delete old expired before new cycle
    delete_last_expired()

    best_market, best_signal, best_confidence = None, None, 0

    for market in MARKETS:
        if len(market_ticks[market]) > 50:
            result = analyze_market(market, market_ticks[market])
            if result:
                signal, confidence = result
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_signal = signal
                    best_market = market

    if best_market and best_signal:
        now = datetime.now()
        next_signal_time = now + timedelta(minutes=1)
        market_name = MARKET_NAMES.get(best_market, best_market)

        # -------- MAIN SIGNAL --------
        entry_digit = int(str(market_ticks[best_market][-1])[-1]) if market_ticks[best_market] else None

        strategy_note = (
            "\n\n🤖 Strategy Focus: <b>Digit Under 6</b>"
            if best_signal == "Under 6"
            else "\n\n🤖 Strategy Focus: <b>Digit Under 8</b>"
        )

        main_msg = (
            f"⚡ <b>KashyTrader Premium Signal</b>\n\n"
            f"⏰ Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 Market: {market_name}\n"
            f"🎯 Signal: <b>{best_signal}</b>\n"
            f"🔢 Entry Point Digit: <b>{entry_digit}</b>\n"
            f"📈 Confidence: <b>{best_confidence:.2%}</b>\n"
            f"🔥 Execute now!"
            f"{strategy_note}"
        )
        send_telegram_message(main_msg)
        time.sleep(120)  # 2 mins duration

        # -------- POST-NOTIFICATION --------
        post_msg = (
            f"✅ <b>Signal Expired</b>\n\n"
            f"📊 Market: {market_name}\n"
            f"🕒 Expired at: {now.strftime('%H:%M:%S')}\n\n"
            f"🔔 Next Signal Expected: {next_signal_time.strftime('%H:%M:%S')}"
        )
        last_expired_id = send_telegram_message(post_msg, keep=True)

        # -------- CLEANUP OLD MESSAGES --------
        time.sleep(30)
        delete_messages()


def on_message(ws, message):
    """Handle incoming tick data."""
    data = json.loads(message)

    if "tick" in data:
        symbol = data["tick"]["symbol"]
        quote = data["tick"]["quote"]

        market_ticks[symbol].append(quote)
        if len(market_ticks[symbol]) > 200:
            market_ticks[symbol].pop(0)


def subscribe_to_ticks(ws):
    for market in MARKETS:
        ws.send(json.dumps({"ticks": market}))


def run_websocket():
    ws = websocket.WebSocketApp(
        DERIV_API_URL,
        on_message=on_message
    )
    ws.on_open = lambda w: subscribe_to_ticks(w)
    ws.run_forever()


def schedule_signals():
    while True:
        fetch_and_analyze()
        time.sleep(600)  # every 10 min


if __name__ == "__main__":
    ws_thread = threading.Thread(target=run_websocket)
    ws_thread.start()
    schedule_signals()
