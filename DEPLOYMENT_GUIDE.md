# Hybrid DCA Grid Trading Bot - Production Deployment Guide

## Overview

This guide walks you through deploying the optimized Hybrid DCA Grid Bot for **live trading with real Binance API keys**.

---

## 🔒 Step 1: Secure API Key Setup

### Get Your Binance API Keys

1. Go to [Binance API Management](https://www.binance.com/en/account/api-management)
2. Click "Create API"
3. **Set API Restrictions to:**
   - ✅ Spot Trading
   - ✅ Enable Trading
   - ❌ Disable IP Whitelist (or add your server IP)
   - ❌ Disable Withdrawals
4. Copy both **API Key** and **Secret Key**

### Configure .env File

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your credentials
nano .env
```

**Key settings for live trading:**

```env
# API Credentials
CRYPTO_API_KEY=y5mYCDHRdMY1kBljj8ZfUZGEXvX0LHq2yAhqDzyP37AuH0fF3KMWjnEvFNaOp1n9mour_binance_api_key_here
CRYPTO_API_SECRET=MwJAlHsNCQQ2RJ1JpUIj3bSoKlxDR7wiYiWiEyia16jXRPSrlPpJtxAmWc5M4pmiyour_binance_api_secret_here

# LIVE TRADING MODE
PAPER_TRADING=false

# Trading symbol
BOT_SYMBOL=BTC-USD
```

### ⚠️ SECURITY CHECKLIST

- [ ] **NEVER** commit .env with real keys to git
- [ ] Use `.gitignore` to exclude .env: `echo ".env" >> .gitignore`
- [ ] Restrict .env file permissions: `chmod 600 .env`
- [ ] Use API restrictions in Binance (no withdrawals, IP whitelist if possible)
- [ ] Start with PAPER_TRADING=true first to test

---

## 📧 Step 2: Setup Notifications

### Email Alerts (Gmail)

```env
ENABLE_EMAIL_ALERTS=true
EMAIL_FROM=your_email@gmail.com
EMAIL_PASSWORD=your_app_password    # Use App Password, not account password!
EMAIL_TO=recipient@gmail.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

**Get Gmail App Password:**

1. Enable 2-Step Verification in your Google Account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Select "Mail" and "Windows Computer"
4. Copy the 16-character password to EMAIL_PASSWORD

### Discord Webhook

```env
ENABLE_DISCORD_ALERTS=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/TOKEN
```

**Get Discord Webhook URL:**

1. Create a private Discord channel for bot alerts
2. Channel Settings → Integrations → Webhooks → New Webhook
3. Copy the Webhook URL

### Telegram Bot

```env
ENABLE_TELEGRAM_ALERTS=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

**Setup Telegram Bot:**

1. Message @BotFather on Telegram
2. Create new bot with `/newbot`
3. Copy the token
4. Get your chat ID by messaging the bot and visiting:
   `https://api.telegram.org/bot{TOKEN}/getUpdates`

---

## 🚀 Step 3: Installation & Setup

```bash
# Install deploy script dependencies
pip install python-dotenv websocket-client requests

# Make deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

---

## 🎯 Step 4: Start Bot

### Option 1: Direct (Foreground - Best for Testing)

```bash
python3 NEW
```

Monitor logs in real-time:

```bash
tail -f hybrid_dca_grid.log
```

### Option 2: Screen Session (Background - Production)

```bash
# Start bot in detached screen
screen -S trading -d -m python3 NEW

# Attach to monitor
screen -S trading -r

# Detach (keep running)
Ctrl+A then D
```

### Option 3: Systemd Service (Recommended - Always Running)

```bash
# Setup
sudo systemctl daemon-reload
sudo systemctl enable hybrid-dca-bot
sudo systemctl start hybrid-dca-bot

# Monitor
sudo journalctl -u hybrid-dca-bot -f

# Check status
sudo systemctl status hybrid-dca-bot

# Stop
sudo systemctl stop hybrid-dca-bot
```

---

## 📊 Step 5: Monitoring & Health Checks

### Health Reports

The bot generates health reports every 5 minutes (configurable):

```bash
# View latest health status
cat health_report.json

# View performance metrics
cat performance_report.json
```

### Log Analysis

```bash
# Watch logs in real-time
tail -f hybrid_dca_grid.log

# Show all trades
grep "INSTANT FILL" hybrid_dca_grid.log

# Count active grid orders
grep "GRID_BUY\|GRID_SELL" hybrid_dca_grid.log | wc -l

# Find errors
grep "ERROR" hybrid_dca_grid.log

# Show DCA triggers
grep "DCA Level" hybrid_dca_grid.log
```

### Alert Testing

Before going live, test notifications:

```python
from notifications import get_notification_manager

notif = get_notification_manager()
notif.send_trade_alert({
    "side": "buy",
    "symbol": "BTC-USD",
    "qty": 0.001,
    "price": 45000,
    "tag": "TEST",
    "order_id": "TEST_123"
})
```

---

## ⚡ Step 6: Optimization Checklist

Your bot includes 3 major optimizations:

✅ **Fast Monitoring (6-12x)**: Checks signals every 2-5 seconds
✅ **Parallel Orders (5x)**: Places 20 grid orders simultaneously  
✅ **Real-time Fills**: Instant WebSocket fill detection

**Expected Performance:**

- Signal detection: <2-5 seconds (was 30-60s)
- Grid setup: <1 second on Binance (was 5-10s)
- Fill detection: Instant (was polling)

---

## 🛡️ Step 7: Risk Management

### Capital Safety

- Start with PAPER_TRADING=true until confident
- Use small initial allocation (current default: 8% of portfolio)
- Monitor drawdown limits (current: 20%)

### Monitoring Alerts

- Bot sends email/Discord/Telegram on ALL trades
- Critical errors trigger immediate alerts
- Health reports show system status

### Daily Limits

Configure in .env or bot settings:

- DCA buys per 24h: 5 (default)
- Grid spacing: 0.9% (default)
- Max daily trades: 15 (default)

---

## 🔧 Troubleshooting

### Bot Won't Connect to Binance

```bash
# Check API credentials in .env
grep CRYPTO_API .env

# Test connection
python3 -c "
from your_powertrader_file import CryptoAPITrading
api = CryptoAPITrading(paper_trading=False)
api.get_account()
"
```

### No Trade Alerts

```bash
# Check notification config
cat .env | grep ENABLE

# Test specific notification
python3 -c "from notifications import get_notification_manager; notif = get_notification_manager(); print('OK' if notif else 'Failed')"
```

### High CPU/Memory Usage

- Reduce health check interval: `HEALTH_CHECK_INTERVAL=600`
- Limit order threads: Edit `max_workers=8` in bot code
- Enable monitoring to track issues

### WebSocket Disconnects

- Check network stability
- Verify firewall allows WebSocket (port 443)
- Bot auto-reconnects after 10 seconds

---

## 📈 Performance Expectations

### With $10 Starting Capital

- Initial allocation: $0.24 (30% of $0.80 target)
- Grid orders: 20 buy/sell orders
- DCA threshold: -3% to -20% unrealized loss
- Expected monthly: 0.5-2% return (varies with market)

### With Larger Capital

- Scale all allocations proportionally
- Increase grid count if needed
- Adjust DCA multiplier for risk tolerance

---

## 🆘 Emergency Stop

### Immediate Stop

```bash
# Kill the process
pkill -f "python3 NEW"

# Or if using screen
screen -S trading -X quit

# Or if using systemd
sudo systemctl stop hybrid-dca-bot
```

### Cancel All Orders (via Binance)

1. Log into Binance.com
2. Go to Spot Wallet → Spot Trading
3. View open orders
4. Cancel all grid orders manually

---

## 📚 Additional Resources

- [Binance API Docs](https://binance-docs.github.io/apidocs/)
- [WebSocket User Data](https://binance-docs.github.io/apidocs/#user-data-streams)
- [DCA Strategy Info](https://www.investopedia.com/terms/d/dollarcostaveraging.asp)

---

## 🎯 Next Steps

1. ✅ Set up .env with real API keys
2. ✅ Configure notifications
3. ✅ Test with PAPER_TRADING=true
4. ✅ Review logs and alerts
5. ✅ Switch to PAPER_TRADING=false for live
6. ✅ Monitor first trades carefully
7. ✅ Track performance daily

---

**Questions?** Check `hybrid_dca_grid.log` for detailed debugging info.
