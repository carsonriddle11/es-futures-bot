import time
import requests
from datetime import datetime
import pytz

ALPACA_KEY = 'PKV5SQY5PQIJONIKE2BSVTXZXK'
ALPACA_SECRET = 'mrXERbweFVk8L6mJo6dvNutNbiDaH6N4ZKntMYEuu5h'
ALPACA_BASE = 'https://paper-api.alpaca.markets/v2'
DATA_BASE = 'https://data.alpaca.markets/v2'
TRADE_SYMBOL = 'SPY'
DATA_SYMBOL = 'SPY'
QTY = 1
STOP_PCT = 0.003
TP_PCT = 0.006
CHECK_INTERVAL = 60

def alpaca_get(path):
    r = requests.get(ALPACA_BASE + path, headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}, timeout=10)
    r.raise_for_status()
    return r.json()

def alpaca_post(path, body):
    r = requests.post(ALPACA_BASE + path, headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET, 'Content-Type': 'application/json'}, json=body, timeout=10)
    r.raise_for_status()
    return r.json()

def get_bars():
    try:
        r = requests.get(DATA_BASE + '/stocks/' + DATA_SYMBOL + '/bars', headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}, params={'timeframe': '15Min', 'limit': 100, 'feed': 'iex'}, timeout=10)
        if r.status_code != 200:
            print('Data error: ' + str(r.status_code) + ' ' + r.text)
            return None
        bars = r.json().get('bars', [])
        if not bars or len(bars) < 30:
            print('Not enough bars: ' + str(len(bars)))
            return None
        return [b['c'] for b in bars], [b['v'] for b in bars]
    except Exception as e:
        print('get_bars error: ' + str(e))
        return None

def ema(data, period):
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    if len(gains) < period:
        return 50
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100 - 100 / (1 + ag / (al or 0.001))

def get_signal(closes, volumes):
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    rsi_val = rsi(closes)
    avg_vol = sum(v or 0 for v in volumes[-20:]) / 20
    vol_ratio = (volumes[-1] or 0) / (avg_vol or 1)
    print('EMA9:' + str(round(e9[-1],2)) + ' EMA21:' + str(round(e21[-1],2)) + ' RSI:' + str(round(rsi_val,1)) + ' Vol:' + str(round(vol_ratio,2)) + 'x')
    if e9[-1] > e21[-1] and 45 < rsi_val < 75 and vol_ratio > 0.7:
        return 'long', 'EMA bull | RSI ' + str(round(rsi_val,1))
    elif e9[-1] < e21[-1] and 25 < rsi_val < 55 and vol_ratio > 0.7:
        return 'short', 'EMA bear | RSI ' + str(round(rsi_val,1))
    return 'flat', 'No signal'

def is_market_hours():
    et = datetime.now(pytz.timezone('America/New_York'))
    h, m, wd = et.hour, et.minute, et.weekday()
    if wd >= 5:
        return False
    return (h == 9 and m >= 30) or (10 <= h < 16)

def get_position():
    try:
        return alpaca_get('/positions/' + TRADE_SYMBOL)
    except:
        return None

def has_open_order():
    try:
        orders = alpaca_get('/orders?status=open&limit=50')
        return any(o.get('symbol') == TRADE_SYMBOL for o in orders)
    except:
        return False

def place_order(side, price):
    sp = round(price * (1 - STOP_PCT) if side == 'buy' else price * (1 + STOP_PCT), 2)
    tp = round(price * (1 + TP_PCT) if side == 'buy' else price * (1 - TP_PCT), 2)
    try:
        o = alpaca_post('/orders', {'symbol': TRADE_SYMBOL, 'qty': str(QTY), 'side': side, 'type': 'market', 'time_in_force': 'day', 'order_class': 'bracket', 'stop_loss': {'stop_price': str(sp)}, 'take_profit': {'limit_price': str(tp)}})
        print('ORDER PLACED: ' + side.upper() + ' ' + TRADE_SYMBOL + ' @ ' + str(price) + ' SL:' + str(sp) + ' TP:' + str(tp))
        return o
    except Exception as e:
        print('ORDER FAILED: ' + str(e))
        return None

def main():
    print('ES FUTURES BOT STARTING')
    try:
        acct = alpaca_get('/account')
        print('Connected | Equity: $' + str(round(float(acct['equity']), 2)))
    except Exception as e:
        print('Connection failed: ' + str(e))
        raise

    last_signal = 'flat'
    check_count = 0

    while True:
        try:
            et = datetime.now(pytz.timezone('America/New_York'))
            check_count += 1
            print('[' + et.strftime('%H:%M:%S ET') + '] Check #' + str(check_count))

            if not is_market_hours():
                print('Outside market hours (9:30am-4pm ET weekdays)')
                time.sleep(CHECK_INTERVAL)
                continue

            result = get_bars()
            if not result:
                time.sleep(CHECK_INTERVAL)
                continue

            closes, volumes = result
            price = closes[-1]
            print('Price: ' + str(round(price, 2)))

            signal, reason = get_signal(closes, volumes)
            print('Signal: ' + signal.upper() + ' | ' + reason)

            position = get_position()
            open_order = has_open_order()

            if position:
                pnl = float(position.get('unrealized_pl', 0))
                print('Position open | PnL: $' + str(round(pnl, 2)))

            if signal != 'flat' and signal != last_signal and not position and not open_order:
                side = 'buy' if signal == 'long' else 'sell'
                print('NEW SIGNAL - placing ' + side.upper())
                place_order(side, price)

            last_signal = signal

        except Exception as e:
            print('Loop error: ' + str(e))

        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
