import time, sys
import requests

KEY = 'PKFLIK7LVILZVQ5RMPMYGI6FEN'
SEC = '5FygYR2pMMbcZLHb93DszZivRnNd3g8TTB716BgQ2qfR'
BASE = 'https://paper-api.alpaca.markets/v2'
DATA = 'https://data.alpaca.markets/v2'
SYMBOL = 'SPY'
QTY = 1
STOP_PCT = 0.003
TP_PCT = 0.006

def p(msg):
    print(msg, flush=True)
    sys.stdout.flush()

def headers():
    return {'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SEC}

def get_account():
    r = requests.get(BASE + '/account', headers=headers(), timeout=10)
    return r.json()

def get_bars():
    r = requests.get(DATA + '/stocks/' + SYMBOL + '/bars', headers=headers(), params={'timeframe': '15Min', 'limit': 100, 'feed': 'iex'}, timeout=10)
    bars = r.json().get('bars', [])
    if len(bars) < 30:
        return None
    return [b['c'] for b in bars], [b['v'] for b in bars]

def ema(data, period):
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result

def get_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(0, d))
        losses.append(max(0, -d))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100 - 100 / (1 + ag / (al or 0.001))

def get_signal(closes, volumes):
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    rsi = get_rsi(closes)
    avg_vol = sum(volumes[-20:]) / 20
    vol = volumes[-1] / (avg_vol or 1)
    if e9[-1] > e21[-1] and 45 < rsi < 75 and vol > 0.7:
        return 'long'
    if e9[-1] < e21[-1] and 25 < rsi < 55 and vol > 0.7:
        return 'short'
    return 'flat'

def is_market_hours():
    from datetime import datetime
    import pytz
    et = datetime.now(pytz.timezone('America/New_York'))
    h, m, wd = et.hour, et.minute, et.weekday()
    if wd >= 5:
        return False
    return (h == 9 and m >= 30) or (10 <= h < 16)

def get_position():
    try:
        r = requests.get(BASE + '/positions/' + SYMBOL, headers=headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None

def place_order(side, price):
    sp = round(price * (1 - STOP_PCT) if side == 'buy' else price * (1 + STOP_PCT), 2)
    tp = round(price * (1 + TP_PCT) if side == 'buy' else price * (1 - TP_PCT), 2)
    body = {'symbol': SYMBOL, 'qty': str(QTY), 'side': side, 'type': 'market', 'time_in_force': 'day', 'order_class': 'bracket', 'stop_loss': {'stop_price': str(sp)}, 'take_profit': {'limit_price': str(tp)}}
    r = requests.post(BASE + '/orders', headers=headers(), json=body, timeout=10)
    p('ORDER: ' + side.upper() + ' @ ' + str(price) + ' SL:' + str(sp) + ' TP:' + str(tp))
    return r.json()

def main():
    p('BOT STARTING')
    try:
        acct = get_account()
        p('Connected | Equity: ' + str(acct.get('equity', 'unknown')))
    except Exception as e:
        p('Connection failed: ' + str(e))
        raise
    last = 'flat'
    while True:
        try:
            if not is_market_hours():
                p('Market closed - waiting')
                time.sleep(60)
                continue
            result = get_bars()
            if not result:
                p('No data')
                time.sleep(60)
                continue
            closes, volumes = result
            price = closes[-1]
            signal = get_signal(closes, volumes)
            p('Price:' + str(round(price, 2)) + ' Signal:' + signal)
            position = get_position()
            if position:
                p('Position open | PnL:' + str(round(float(position.get('unrealized_pl', 0)), 2)))
            if signal != 'flat' and signal != last and not position:
                side = 'buy' if signal == 'long' else 'sell'
                place_order(side, price)
            last = signal
        except Exception as e:
            p('Error: ' + str(e))
        time.sleep(60)

if __name__ == '__main__':
    main()