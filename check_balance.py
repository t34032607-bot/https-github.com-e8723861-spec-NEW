#!/usr/bin/env python3
import os
import sys

# Load from .env
os.chdir('/workspaces/NEW')
sys.path.insert(0, '/workspaces/NEW')

from dotenv import load_dotenv
load_dotenv('/workspaces/NEW/.env')

from your_powertrader_file import CryptoAPITrading

api = CryptoAPITrading(paper_trading=False)
acct = api.get_account()

if isinstance(acct, dict):
    buying_power = float(acct.get("buying_power", 0))
    balance = float(acct.get("balance", 0))
    print(f"\n💰 Spot Account Balance:")
    print(f"Available USD: ${buying_power:.2f}")
    print(f"Total Balance: ${balance:.2f}")
else:
    print(f"Response: {acct}")
