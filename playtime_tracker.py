"""Playtime tracking and statistics module."""

import time
from typing import Dict, List, Tuple

from crypto import Account


class PlaytimeTracker:
    """Tracks playtime for active game sessions."""

    def __init__(self):
        """Initialize tracker."""
        self.active_sessions: Dict[int, Tuple[float, str]] = {}  # {handle: (start_time, username)}

    def start_session(self, handle: int, username: str) -> None:
        """Start tracking a new playtime session."""
        self.active_sessions[handle] = (time.time(), username)

    def end_session(self, handle: int) -> float:
        """End a playtime session and return duration in seconds."""
        if handle not in self.active_sessions:
            return 0.0
        
        start_time, _ = self.active_sessions.pop(handle)
        duration = time.time() - start_time
        return max(0.0, duration)

    def get_session_duration(self, handle: int) -> float:
        """Get current session duration without ending it."""
        if handle not in self.active_sessions:
            return 0.0
        
        start_time, _ = self.active_sessions[handle]
        return time.time() - start_time

    def update_account_playtime(
        self, account: Account, session_duration: float
    ) -> Account:
        """Update account with new session playtime."""
        account.total_playtime += session_duration
        account.sessions_count += 1
        account.last_used = time.time()
        return account

    def format_playtime(self, seconds: float) -> str:
        """Format seconds to human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds) // 60
            secs = int(seconds) % 60
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds) // 3600
            minutes = (int(seconds) % 3600) // 60
            return f"{hours}h {minutes}m"

    def get_account_stats(self, account: Account) -> Dict[str, str]:
        """Get formatted playtime statistics for an account."""
        return {
            "name": account.name,
            "username": account.username,
            "total_playtime": self.format_playtime(account.total_playtime),
            "total_seconds": account.total_playtime,
            "sessions": account.sessions_count,
            "avg_session": (
                self.format_playtime(account.total_playtime / max(1, account.sessions_count))
            ),
        }

    def get_accounts_stats_sorted(
        self, accounts: List[Account], sort_by: str = "playtime"
    ) -> List[Dict[str, str]]:
        """Get sorted playtime statistics for all accounts."""
        stats_list = [self.get_account_stats(acc) for acc in accounts]
        
        if sort_by == "playtime":
            stats_list.sort(key=lambda x: x["total_seconds"], reverse=True)
        elif sort_by == "sessions":
            stats_list.sort(key=lambda x: x["sessions"], reverse=True)
        elif sort_by == "name":
            stats_list.sort(key=lambda x: x["name"])
        
        return stats_list
