"""Discord Webhook integration for session notifications."""

import logging
import json
import requests
from typing import Optional
from datetime import datetime


class DiscordIntegration:
    """Send session start/end notifications to Discord webhook."""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Discord integration.
        
        Args:
            webhook_url: Discord webhook URL (if None, notifications disabled)
        """
        self.logger = logging.getLogger("discord")
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def set_webhook_url(self, url: str) -> None:
        """
        Set or update Discord webhook URL.
        
        Args:
            url: Discord webhook URL
        """
        self.webhook_url = url
        self.enabled = bool(url)
        self.logger.info(f"Discord webhook {'enabled' if self.enabled else 'disabled'}")

    def send_session_started(self, account_name: str, username: str, region: str) -> bool:
        """
        Send notification when session starts.
        
        Args:
            account_name: Account display name
            username: Wizard101 username
            region: Region code (de, us, etc.)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        embed = {
            "title": f"🎮 Wizard101 Session Started",
            "description": f"**Account:** {account_name}\n**Username:** {username}\n**Region:** {region.upper()}",
            "color": 2151936,  # Dark teal
            "timestamp": datetime.now().isoformat(),
        }
        
        return self._send_embed(embed)

    def send_session_ended(self, account_name: str, playtime_minutes: float) -> bool:
        """
        Send notification when session ends.
        
        Args:
            account_name: Account display name
            playtime_minutes: Session duration in minutes
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        hours = int(playtime_minutes // 60)
        minutes = int(playtime_minutes % 60)
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        embed = {
            "title": f"⏹️ Wizard101 Session Ended",
            "description": f"**Account:** {account_name}\n**Playtime:** {duration_str}",
            "color": 10181046,  # Light orange
            "timestamp": datetime.now().isoformat(),
        }
        
        return self._send_embed(embed)

    def send_custom_message(self, title: str, message: str, color: int = 3447003) -> bool:
        """
        Send custom message to Discord.
        
        Args:
            title: Embed title
            message: Embed message
            color: Embed color (default: blue)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.now().isoformat(),
        }
        
        return self._send_embed(embed)

    def _send_embed(self, embed: dict) -> bool:
        """
        Send Discord embed message via webhook.
        
        Args:
            embed: Discord embed dictionary
            
        Returns:
            True if successful
        """
        if not self.webhook_url:
            return False
        
        try:
            payload = {"embeds": [embed]}
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=5
            )
            
            if response.status_code in [200, 204]:
                self.logger.debug("Discord notification sent")
                return True
            else:
                self.logger.warning(f"Discord webhook returned {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Discord webhook failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Discord integration error: {e}")
            return False

    def test_connection(self) -> bool:
        """
        Test Discord webhook connection.
        
        Returns:
            True if connection successful
        """
        if not self.webhook_url:
            return False
        
        return self.send_custom_message(
            "🧪 Wiz Q Launcher - Test Notification",
            "Discord webhook connection is working!",
            color=3447003
        )
