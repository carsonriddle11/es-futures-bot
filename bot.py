import time
import requests
from datetime import datetime
import pytz

ALPACA_KEY = 'PKDA75ZWIQFEN4DBSS5UFHBCGW'
ALPACA_SECRET = '79C3H1cJvevNDEZexb8wYS9QqTXueXFokuTVSg3J6t9C'
ALPACA_BASE = 'https://paper-api.alpaca.markets/v2'
SYMBOL = 'MES'
QTY = 1
STOP_LOSS_PTS = 10
TAKE_PROFIT_PTS = 20
CHECK_INTERVAL = 60
STRATEGY = 'ema_rsi'

def alpaca_get(path):
    r = requests.get(ALPACA_BASE + path, headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET})
    r.raise_for_status()
    return r.json()

def alpaca_post(path, body):
    r = requests.post(ALPACA_BASE + path, headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET, 'Content-Type': 'application/json'}, json=body)
    r.raise_for_status()
    return r.json()

def get_bars(symbol, timeframe='15Min', limit=100):
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/{symbol}/bars', headers={'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}, params={'timeframe': timeframe, 'limit': limit, 'feed': 'iex'})
    if r.status_code != 200:
        return None
    bars = r.json().get('bars', [])
    if not bars:
        return None
    return [b['c'] for b in bars], [b['v'] for b in bars]

def ema(data, period):
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return [50] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    result = [None] * period
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    result.append(100 - 100 / (1 + ag / (al or 0.001)))
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        result.append(100 - 100 / (1 + ag / (al or 0.001)))
    return result

def macd(closes):
    ef = ema(closes, 12)
    es = ema(closes, 26)
    ml = [f - s for f, s in zip(ef, es)]
    sl = ema(ml[25:], 9)
    return ml, [None] * 25 + sl

def bollinger(closes, period=20):
    upper, middle, lower = [], [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None); middle.append(None); lower.append(None)
            continue
        sl = closes[i - period + 1:i + 1]
        mn = sum(sl) / period
        sd = (sum((x - mn) ** 2 for x in sl) / period) ** 0.5
        upper.append(mn + 2 * sd); middle.append(mn); lower.append(mn - 2 * sd)
    return upper, middle, lower

def vwap(prices, volumes):
    ct, cv, result = 0, 0, []
    for p, v in zip(prices, volumes):
        ct += p * (v or 0); cv += (v or 0)
        result.append(ct / cv if cv > 0 else p)
    return result

def get_signal(closes, volumes):
    if len(closes) < 30:
        return 'flat', 'Not enough data'
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    rv = rsi(closes, 14)
    avg_vol = sum(v or 0 for v in volumes[-20:]) / 20
    last = len(closes) - 1
    price = closes[last]
    rsi_val = rv[last]
    vol_ratio = (volumes[last] or 0) / (avg_vol or 1)
    if e9[last] > e21[last] and 45 < rsi_val < 75 and vol_ratio > 0.7:
        return 'long', f'EMA bull | RSI {rsi_val:.1f} | Vol {vol_ratio:.2f}x'
    elif e9[last] < e21[last] and 25 < rsi_val < 55 and vol_ratio > 0.7:
        return 'short', f'EMA bear | RSI {rsi_val:.1f} | Vol {vol_ratio:.2f}x'
    return 'flat', f'No signal | RSI {rsi_val:.1f} | Vol {vol_ratio:.2f}x'

def is_market_hours():
    et = datetime.now(pytz.timezone('America/New_York'))
    h, wd = et.hour, et.weekday()
    if wd == 5: return False
    if wd == 6 and h < 18: return False
    return (9 <= h < 16) or (18 <= h <= 23)

def get_position():
    try:
        return alpaca_get(f'/positions/{SYMBOL}')
    except:
        return None

def has_open_order():
    try:
        orders = alpaca_get('/orders?status=open')
        return any(o['symbol'] == SYMBOL for o in orders)
    except:
        return False

def place_order(side, price):
    sp = price - STOP_LOSS_PTS if side == 'buy' else price + STOP_LOSS_PTS
    tp = price + TAKE_PROFIT_PTS if side == 'buy' else price - TAKE_PROFIT_PTS
    try:
        o = alpaca_post('/orders', {'symbol': SYMBOL, 'qty': str(QTY), 'side': side, 'type': 'market', 'time_in_force': 'day', 'order_class': 'bracket', 'stop_loss': {'stop_price': str(round(sp, 2))}, 'take_profit': {'limit_price': str(round(tp, 2))}})
        print(f'  ORDER PLACED: {o["id"][:8]} | {side.upper()} {QTY}x {SYMBOL} @ {price:.2f} | SL:{sp:.2f} TP:{tp:.2f}')
        return o
    except Exception as e:
        print(f'  ORDER FAILED: {e}')
        return None

def main():
    print('ES FUTURES BOT STARTING...')
    try:
        acct = alpaca_get('/account')
        print(f'Connected | Equity: ${float(acct["equity"]):,.2f}')
    except Exception as e:
        print(f'Connection failed: {e}')
        return
    last_signal = 'flat'
    while True:
        try:
            et = datetime.now(pytz.timezone('America/New_York'))
            print(f'\n[{et.strftime("%Y-%m-%d %H:%M:%S ET")}]')
            if not is_market_hours():
                print('  Outside trading hours - waiting...')
                time.sleep(CHECK_INTERVAL)
                continue
            result = get_bars(SYMBOL)
            if not result:
                print('  No data')
                time.sleep(CHECK_INTERVAL)
                continue
            closes, volumes = result
            price = closes[-1]
            signal, reason = get_signal(closes, volumes)
            print(f'  Price: {price:.2f} | Signal: {signal.upper()} | {reason}')
            position = get_position()
            open_order = has_open_order()
            if position:
                print(f'  Position open | P&L: ${float(position.get("unrealized_pl", 0)):.2f}')
            if signal != 'flat' and signal != last_signal and not position and not open_order:
                side = 'buy' if signal == 'long' else 'sell'
                print(f'  NEW SIGNAL - placing {side.upper()}...')
                place_order(side, price)
            last_signal = signal
        except KeyboardInterrupt:
            print('Bot stopped.')
            break
        except Exception as e:
            print(f'  Error: {e}')
        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
