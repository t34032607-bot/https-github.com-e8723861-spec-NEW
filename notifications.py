"""
Notification system for trade alerts and monitoring
Supports: Email, Discord, Telegram, Slack webhooks
"""

import os
import json
import logging
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger("Notifications")

class NotificationManager:
    """Handle all notification channels for trades and alerts"""
    
    def __init__(self):
        self.email_enabled = os.getenv("ENABLE_EMAIL_ALERTS", "false").lower() == "true"
        self.discord_enabled = os.getenv("ENABLE_DISCORD_ALERTS", "false").lower() == "true"
        self.telegram_enabled = os.getenv("ENABLE_TELEGRAM_ALERTS", "false").lower() == "true"
        self.webhook_enabled = os.getenv("ENABLE_WEBHOOK_ALERTS", "false").lower() == "true"
        
        # Email config
        self.email_from = os.getenv("EMAIL_FROM")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        self.email_to = os.getenv("EMAIL_TO")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        
        # Discord config
        self.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
        
        # Telegram config
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        # Webhook config (Slack, etc)
        self.webhook_url = os.getenv("WEBHOOK_URL")
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate notification configuration"""
        if self.email_enabled:
            if not all([self.email_from, self.email_password, self.email_to]):
                logger.warning("Email alerts enabled but missing configuration")
                self.email_enabled = False
            else:
                logger.info(f"✅ Email alerts configured: {self.email_to}")
        
        if self.discord_enabled:
            if not self.discord_webhook:
                logger.warning("Discord alerts enabled but webhook URL missing")
                self.discord_enabled = False
            else:
                logger.info("✅ Discord alerts configured")
        
        if self.telegram_enabled:
            if not all([self.telegram_token, self.telegram_chat_id]):
                logger.warning("Telegram alerts enabled but credentials missing")
                self.telegram_enabled = False
            else:
                logger.info(f"✅ Telegram alerts configured: Chat {self.telegram_chat_id}")
        
        if self.webhook_enabled:
            if not self.webhook_url:
                logger.warning("Webhook alerts enabled but URL missing")
                self.webhook_enabled = False
            else:
                logger.info("✅ Webhook alerts configured")
    
    def send_trade_alert(self, trade_data: Dict[str, Any]):
        """Send trade execution alert"""
        message = self._format_trade_message(trade_data)
        
        if self.email_enabled:
            self._send_email(f"Trade Alert: {trade_data['side'].upper()}", message)
        
        if self.discord_enabled:
            self._send_discord(message, trade_data.get("side", "UNKNOWN"))
        
        if self.telegram_enabled:
            self._send_telegram(message)
        
        if self.webhook_enabled:
            self._send_webhook(message, trade_data)
    
    def send_dca_alert(self, level: float, symbol: str):
        """Send DCA trigger alert"""
        message = f"🚀 DCA TRIGGERED: {symbol} at level {level}%\nTime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        if self.discord_enabled:
            self._send_discord(message, "DCA", color=0xFF9900)
        
        if self.telegram_enabled:
            self._send_telegram(message)
        
        if self.email_enabled:
            self._send_email(f"DCA Alert: {symbol} Level {level}%", message)
    
    def send_profit_release_alert(self, profit_pct: float, symbol: str):
        """Send profit release/take profit alert"""
        message = f"💰 PROFIT RELEASE: {symbol} Profit: {profit_pct:.2f}%\nTime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        if self.discord_enabled:
            self._send_discord(message, "PROFIT", color=0x00FF00)
        
        if self.telegram_enabled:
            self._send_telegram(message)
        
        if self.email_enabled:
            self._send_email(f"Profit Release: {symbol} {profit_pct:.2f}%", message)
    
    def send_error_alert(self, error_message: str):
        """Send critical error alert"""
        message = f"⚠️ BOT ERROR:\n{error_message}\nTime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        if self.discord_enabled:
            self._send_discord(message, "ERROR", color=0xFF0000)
        
        if self.telegram_enabled:
            self._send_telegram(message)
        
        if self.email_enabled:
            self._send_email("CRITICAL: Bot Error Alert", message)
    
    def _format_trade_message(self, trade_data: Dict[str, Any]) -> str:
        """Format trade data into readable message"""
        return f"""
📊 TRADE EXECUTED
━━━━━━━━━━━━━━━━━━━
Side: {trade_data.get('side', 'N/A').upper()}
Symbol: {trade_data.get('symbol', 'N/A')}
Quantity: {trade_data.get('qty', 0):.8f}
Price: ${trade_data.get('price', 0):.2f}
Cost: ${trade_data.get('qty', 0) * trade_data.get('price', 0):.2f}
Tag: {trade_data.get('tag', 'UNKNOWN')}
Order ID: {trade_data.get('order_id', 'N/A')}
━━━━━━━━━━━━━━━━━━━
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    def _send_email(self, subject: str, body: str):
        """Send email alert"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def _send_discord(self, message: str, alert_type: str = "ALERT", color: int = 0x0099FF):
        """Send Discord webhook alert"""
        try:
            embed = {
                "title": f"🤖 {alert_type}",
                "description": message,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            payload = {"embeds": [embed]}
            response = requests.post(self.discord_webhook, json=payload, timeout=5)
            
            if response.status_code == 204:
                logger.debug("✅ Discord message sent")
            else:
                logger.error(f"Discord error: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
    
    def _send_telegram(self, message: str):
        """Send Telegram message"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=5)
            
            if response.status_code == 200:
                logger.debug("✅ Telegram message sent")
            else:
                logger.error(f"Telegram error: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    def _send_webhook(self, message: str, extra_data: Optional[Dict] = None):
        """Send generic webhook alert (Slack, IFTTT, etc)"""
        try:
            payload = {
                "text": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "HybridDCABot"
            }
            
            if extra_data:
                payload.update(extra_data)
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            
            if response.status_code in [200, 201, 204]:
                logger.debug("✅ Webhook message sent")
            else:
                logger.error(f"Webhook error: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


# Initialize notification manager
def get_notification_manager() -> NotificationManager:
    """Get singleton notification manager"""
    if not hasattr(get_notification_manager, '_instance'):
        get_notification_manager._instance = NotificationManager()
    return get_notification_manager._instance
