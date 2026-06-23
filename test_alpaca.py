from alpaca.data.live import CryptoDataStream
from config import CONFIG
import asyncio

async def main():
    stream = CryptoDataStream(CONFIG.alpaca.api_key, CONFIG.alpaca.secret_key)
    
    async def bar_callback(bar):
        print(f"Received bar: {bar}")
        stream.stop()

    stream.subscribe_bars(bar_callback, "BTC/USD")
    
    print("Connecting to Alpaca Crypto WebSocket...")
    await stream._run_forever()

if __name__ == "__main__":
    asyncio.run(main())
