from flask import Flask, request, jsonify
from datetime import datetime
import random

app = Flask(__name__)

# Simulated real-time signal logic (can be replaced with live market data)
def get_fake_signal(pair, timeframe):
    action = random.choice(["BUY", "SELL"])
    confidence = random.randint(75, 95)
    risk = "LOW" if confidence > 85 else "MEDIUM"
    entry_price = round(random.uniform(0.8, 1.5), 5)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    return {
        "pair": pair.replace("_", "/").upper(),
        "action": action,
        "entry_price": f"${entry_price}",
        "expiration": timeframe,
        "confidence": f"{confidence}%",
        "risk_level": risk,
        "analysis": f"Simulated analysis for {pair} on {timeframe}",
        "timestamp": now
    }

@app.route("/get-signal")
def get_signal():
    pair = request.args.get("pair", "EURUSD")
    timeframe = request.args.get("timeframe", "1m")
    signal = get_fake_signal(pair, timeframe)
    return jsonify(signal)

# 🚨 IMPORTANT: Use port 8080 for Railway hosting
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)