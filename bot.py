import time
import requests

KEY = 'PKFLIK7LVILZVQ5RMPMYGI6FEN'
SEC = '5FygYR2pMMbcZLHb93DszZivRnNd3g8TTB716BgQ2qfR'
BASE = 'https://paper-api.alpaca.markets/v2'

while True:
    try:
        r = requests.get(BASE + '/account', headers={'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SEC})
        print(r.json().get('equity', 'no equity'))
    except Exception as e:
        print(str(e))
    time.sleep(60)
