#!/usr/bin/env python3
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from your_powertrader_file import CryptoAPITrading

api = CryptoAPITrading(paper_trading=False)
acct = api.get_account()

if isinstance(acct, dict):
    buying_power = float(acct.get("buying_power", 0))
    balance = float(acct.get("total_account_value", 0))
    print(f"\n💰 Spot Account Balance:")
    print(f"Available USD: ${buying_power:.2f}")
    print(f"Total Account Value: ${balance:.2f}")
    positions = acct.get("positions", {})
    if positions:
        print("\nPositions:")
        for asset, stats in positions.items():
            print(f"  {asset}: free={stats['free']} locked={stats['locked']} total={stats['total']}")
else:
    print(f"Response: {acct}")
