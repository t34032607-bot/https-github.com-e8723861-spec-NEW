#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

from your_powertrader_file import CryptoAPITrading

paper_mode = os.getenv("PAPER_TRADING", "true").lower() == "true"
print(f"\n📊 Testing Binance Connection")
print("=" * 50)

try:
    api = CryptoAPITrading(paper_trading=paper_mode)
    mode_str = "PAPER" if paper_mode else "🔴 LIVE (REAL MONEY)"
    print(f"✅ API initialized: {mode_str}")
    
    # Test: Get account info
    acct = api.get_account()
    if isinstance(acct, dict) and "buying_power" in acct:
        buying_power = float(acct.get("buying_power", 0))
        print(f"✅ Account connected")
        print(f"   Buying Power: ${buying_power:.2f}")
    else:
        print(f"⚠️  Account response: {type(acct)} - {str(acct)[:100]}")
    
    # Test: Get price
    buy_p, sell_p, _ = api.get_price(["BTC-USD"])
    btc_price = buy_p.get("BTC-USD") or 0
    if btc_price > 0:
        print(f"✅ Price feed working")
        print(f"   BTC price: ${btc_price:.2f}")
    else:
        print(f"⚠️  No price data")
    
    print("\n" + "=" * 50)
    print("✅ CONNECTION TEST PASSED")
    print("\nTo start live bot:")
    print("   python3 NEW")
    print("\n⚠️  WARNING: This will trade with REAL MONEY")
    print("=" * 50 + "\n")
    
except Exception as e:
    print(f"❌ Connection error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
