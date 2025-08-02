def analyze_signals(df):
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=10).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "BUY" if last['ema_fast'] > last['ema_slow'] else "SELL"
    reason = [f"EMA crossover {'up' if signal == 'BUY' else 'down'}"]
    confidence = 60  # base

    # Adjust based on RSI
    if signal == "BUY" and last['rsi'] < 35:
        reason.append("RSI supports BUY")
        confidence += 15
    elif signal == "SELL" and last['rsi'] > 65:
        reason.append("RSI supports SELL")
        confidence += 15

    # Adjust based on MACD
    if signal == "BUY" and last['macd'] > 0:
        reason.append("MACD trend supports BUY")
        confidence += 10
    elif signal == "SELL" and last['macd'] < 0:
        reason.append("MACD trend supports SELL")
        confidence += 10

    # Cap confidence between 40–95
    confidence = min(max(confidence, 40), 95)

    return signal, confidence, reason, last['close']