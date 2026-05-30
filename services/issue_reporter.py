"""Error reporting to GitHub issues with Discord fallback."""

import logging
import requests
import traceback
from typing import Optional
from datetime import datetime


class IssueReporter:
    """Report errors to GitHub issues or Discord as fallback."""

    def __init__(
        self,
        github_repo: str = "xLordTime/wiz-q-launcher",
        github_token: Optional[str] = None,
        discord_webhook: Optional[str] = None
    ):
        """
        Initialize issue reporter.
        
        Args:
            github_repo: GitHub repository (owner/name)
            github_token: GitHub personal access token (for private repos)
            discord_webhook: Discord webhook URL as fallback
        """
        self.logger = logging.getLogger("reporter")
        self.github_repo = github_repo
        self.github_token = github_token
        self.discord_webhook = discord_webhook
        self.github_api_url = f"https://api.github.com/repos/{github_repo}/issues"

    def report_error(
        self,
        title: str,
        error: Exception,
        context: Optional[str] = None
    ) -> bool:
        """
        Report an error to GitHub or Discord.
        
        Args:
            title: Issue title
            error: Exception that occurred
            context: Additional context/logs
            
        Returns:
            True if reported successfully
        """
        full_title = f"[AUTO-REPORT] {title}"
        body = self._format_error_body(error, context)
        
        # Try GitHub first
        if self._report_to_github(full_title, body):
            return True
        
        # Fallback to Discord
        if self._report_to_discord(full_title, error, context):
            return True
        
        self.logger.warning(f"Could not report issue: {title}")
        return False

    def report_crash(self, exc_info) -> bool:
        """
        Report application crash.
        
        Args:
            exc_info: Exception info from sys.exc_info()
            
        Returns:
            True if reported successfully
        """
        title = "Application Crash"
        exc_type, exc_value, exc_traceback = exc_info
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        return self.report_error(
            title=title,
            error=Exception(error_msg),
            context="Application crashed unexpectedly"
        )

    def _format_error_body(self, error: Exception, context: Optional[str]) -> str:
        """
        Format error for GitHub issue body.
        
        Args:
            error: Exception
            context: Additional context
            
        Returns:
            Formatted GitHub issue body
        """
        error_msg = f"{type(error).__name__}: {str(error)}"
        
        body = f"""## Error Report

**Error Type:** {type(error).__name__}
**Message:** {str(error)}
**Timestamp:** {datetime.now().isoformat()}

### Stack Trace
```
{traceback.format_exc()}
```
"""
        
        if context:
            body += f"\n### Context\n{context}\n"
        
        body += "\n---\n*This issue was auto-reported by Wiz Q Launcher*"
        
        return body

    def _report_to_github(self, title: str, body: str) -> bool:
        """
        Report issue to GitHub.
        
        Args:
            title: Issue title
            body: Issue body
            
        Returns:
            True if successful
        """
        try:
            headers = {
                "Accept": "application/vnd.github.v3+json",
            }
            
            if self.github_token:
                headers["Authorization"] = f"token {self.github_token}"
            
            payload = {
                "title": title,
                "body": body,
                "labels": ["auto-report", "bug"]
            }
            
            response = requests.post(
                self.github_api_url,
                json=payload,
                headers=headers,
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                issue = response.json()
                self.logger.info(f"Reported to GitHub: {issue.get('html_url')}")
                return True
            else:
                self.logger.warning(f"GitHub API returned {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.debug(f"GitHub reporting failed: {e}")
            return False

    def _report_to_discord(self, title: str, error: Exception, context: Optional[str]) -> bool:
        """
        Report issue to Discord webhook.
        
        Args:
            title: Issue title
            error: Exception
            context: Additional context
            
        Returns:
            True if successful
        """
        if not self.discord_webhook:
            return False
        
        try:
            error_msg = f"{type(error).__name__}: {str(error)}"
            
            embed = {
                "title": f"🚨 {title}",
                "description": f"```\n{error_msg}\n```",
                "fields": [],
                "color": 15158332,  # Red
                "timestamp": datetime.now().isoformat(),
            }
            
            if context:
                embed["fields"].append({
                    "name": "Context",
                    "value": context[:1024],  # Discord limit
                    "inline": False
                })
            
            payload = {"embeds": [embed]}
            response = requests.post(
                self.discord_webhook,
                json=payload,
                timeout=5
            )
            
            if response.status_code in [200, 204]:
                self.logger.info("Reported to Discord")
                return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Discord reporting failed: {e}")
            return False
