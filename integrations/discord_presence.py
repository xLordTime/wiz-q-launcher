"""Discord Rich Presence with rolling 24h activity tracking."""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from pypresence import Presence

    PYPRESENCE_AVAILABLE = True
except Exception:
    Presence = None
    PYPRESENCE_AVAILABLE = False


def format_duration(seconds: float) -> str:
    """Format seconds as a compact h/m/s string."""
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class RollingActivity24h:
    """Tracks active windows and computes union activity over the last 24 hours."""

    def __init__(self, state_file: Path, window_seconds: int = 86400):
        self.logger = logging.getLogger("discord_presence")
        self.state_file = Path(state_file)
        self.window_seconds = window_seconds
        self.intervals: List[Tuple[float, float]] = []
        self.active_since: Optional[float] = None
        self._load()

    def _load(self) -> None:
        """Load persisted intervals from disk."""
        if not self.state_file.exists():
            return

        try:
            with self.state_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            loaded = []
            for item in data.get("intervals", []):
                if not isinstance(item, list) or len(item) != 2:
                    continue
                start, end = float(item[0]), float(item[1])
                if end > start:
                    loaded.append((start, end))
            self.intervals = loaded

            active_since = data.get("active_since")
            if active_since is not None:
                # If the app crashed while tracking, close the interval at startup.
                now = time.time()
                start = float(active_since)
                if now > start:
                    self.intervals.append((start, now))
                self.active_since = None

            self._merge_intervals()
            self._prune(time.time())
            self._save()
        except Exception as exc:
            self.logger.warning("Failed to load activity tracker state: %s", exc)

    def _save(self) -> None:
        """Persist tracker state."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "intervals": [[start, end] for start, end in self.intervals],
                "active_since": self.active_since,
            }
            with self.state_file.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception as exc:
            self.logger.debug("Failed to save activity tracker state: %s", exc)

    def _merge_intervals(self) -> None:
        """Merge overlapping or adjacent intervals."""
        if not self.intervals:
            return

        merged = []
        for start, end in sorted(self.intervals, key=lambda x: x[0]):
            if not merged:
                merged.append((start, end))
                continue

            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))

        self.intervals = merged

    def _prune(self, now: float) -> None:
        """Keep only data relevant for the rolling window."""
        cutoff = now - self.window_seconds
        kept = []
        for start, end in self.intervals:
            if end <= cutoff:
                continue
            kept.append((max(start, cutoff), end))
        self.intervals = kept

    def set_active(self, is_active: bool, now: Optional[float] = None) -> None:
        """Update active state; stores transitions only."""
        if now is None:
            now = time.time()

        changed = False
        if is_active and self.active_since is None:
            self.active_since = now
            changed = True
        elif not is_active and self.active_since is not None:
            if now > self.active_since:
                self.intervals.append((self.active_since, now))
            self.active_since = None
            self._merge_intervals()
            changed = True

        self._prune(now)
        if changed:
            self._save()

    def get_total_last_24h(self, now: Optional[float] = None) -> float:
        """Return union active time over the last 24h."""
        if now is None:
            now = time.time()

        cutoff = now - self.window_seconds
        total = 0.0
        for start, end in self.intervals:
            overlap_start = max(start, cutoff)
            overlap_end = min(end, now)
            if overlap_end > overlap_start:
                total += overlap_end - overlap_start

        if self.active_since is not None:
            overlap_start = max(self.active_since, cutoff)
            if now > overlap_start:
                total += now - overlap_start

        return max(0.0, total)

    def close(self) -> None:
        """Finalize tracker state on shutdown."""
        self.set_active(False)


class DiscordRichPresence:
    """Discord Rich Presence client for live playtime status updates."""

    def __init__(
        self,
        client_id: str,
        enabled: bool = True,
        update_interval_seconds: int = 15,
        rpc_yield_to_game: bool = True,
    ):
        self.logger = logging.getLogger("discord_presence")
        self.client_id = str(client_id or "").strip()
        self.enabled = bool(enabled)
        self.update_interval_seconds = max(5, int(update_interval_seconds))
        # When True: clear our RPC while Wizard101 windows are open so Discord's
        # automatic game-detection can show "Playing Wizard101" uninterrupted.
        self.rpc_yield_to_game = bool(rpc_yield_to_game)
        self._rpc = None
        self._connected = False
        self._last_update = 0.0
        self._last_skip_reason: Optional[str] = None
        self._last_connect_error_log = 0.0
        self._last_update_error_log = 0.0
        self._yielding_to_game = False

    def _log_skip_once(self, reason: str, message: str) -> None:
        """Avoid repeating the same skip reason every update interval."""
        if self._last_skip_reason != reason:
            self.logger.info(message)
            self._last_skip_reason = reason

    def connect(self) -> bool:
        """Connect to local Discord RPC endpoint."""
        if not self.enabled:
            self._log_skip_once("disabled", "Discord RPC skipped: disabled in config")
            return False

        if not self.client_id:
            self._log_skip_once("missing_client_id", "Discord RPC skipped: missing client ID")
            return False

        if not PYPRESENCE_AVAILABLE:
            self._log_skip_once("missing_dependency", "Discord RPC skipped: pypresence not available")
            return False

        if self._connected:
            self._last_skip_reason = None
            return True

        try:
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            self._last_skip_reason = None
            self.logger.info("Discord Rich Presence connected")
            return True
        except Exception as exc:
            now = time.time()
            # Throttle connect errors to avoid log spam when Discord is closed.
            if now - self._last_connect_error_log >= 60:
                self.logger.warning("Discord Rich Presence connect failed: %s", exc)
                self._last_connect_error_log = now
            self._connected = False
            self._rpc = None
            return False

    def update_presence(
        self,
        total_24h_seconds: float,
        selected_account_name: Optional[str],
        selected_session_seconds: float,
        active_sessions_count: int,
        region: str,
        total_account_playtime_seconds: float = 0.0,
    ) -> None:
        """
        Update Discord Rich Presence.

        When *rpc_yield_to_game* is True and at least one Wizard101 window is
        active, the presence is cleared so Discord's automatic game-detection
        can show "Playing Wizard101" uninterrupted.  Presence resumes
        automatically once all game windows are closed.

        The *total_account_playtime_seconds* is the cumulative playtime stored
        on the selected account (all-time, not just 24 h).
        """
        if not self.enabled:
            self._log_skip_once("disabled", "Discord RPC update skipped: disabled in config")
            return

        now = time.time()
        if now - self._last_update < self.update_interval_seconds:
            return

        self._last_update = now

        # ── Yield to Discord's Wizard101 auto-detection while game is running ──
        if self.rpc_yield_to_game and active_sessions_count > 0:
            if not self._yielding_to_game:
                self._yielding_to_game = True
                # Clearing our presence lets Discord's process-based game
                # detection take over and show "Playing Wizard101" again.
                if self._connected and self._rpc is not None:
                    try:
                        self._rpc.clear()
                    except Exception:
                        pass
                self.logger.info(
                    "Discord RPC yielded: %d Wizard101 session(s) active — "
                    "game detection enabled",
                    active_sessions_count,
                )
            self._log_skip_once(
                "yield_to_game",
                "Discord RPC idle: yielding to Wizard101 game detection",
            )
            return

        # Resume from yield when all game windows are gone.
        if self._yielding_to_game:
            self._yielding_to_game = False
            self._last_skip_reason = None
            self.logger.info("Discord RPC resuming: no active Wizard101 sessions")

        if not self.connect():
            return

        # ── Build presence strings ────────────────────────────────────────────
        total_acc_str = (
            format_duration(total_account_playtime_seconds)
            if total_account_playtime_seconds > 0
            else None
        )

        details = "Wizard101 Launcher"
        state = f"24h active: {format_duration(total_24h_seconds)}"

        if selected_account_name and selected_session_seconds > 0:
            details = "Playing Wizard101"
            state = f"{selected_account_name}  |  Session: {format_duration(selected_session_seconds)}"
            if total_acc_str:
                state += f"  |  Total: {total_acc_str}"
        elif selected_account_name:
            details = "Wizard101 Launcher"
            state = f"Selected: {selected_account_name}"
            if total_acc_str:
                state += f"  |  Total: {total_acc_str}"

        payload: dict = {
            "details": details,
            "state": state,
            "large_text": (
                f"Region {str(region).upper()}  |  "
                f"24h active: {format_duration(total_24h_seconds)}"
            ),
        }

        if selected_session_seconds > 0:
            payload["start"] = int(now - selected_session_seconds)

        try:
            self._rpc.update(**payload)
            self._last_skip_reason = None
            self.logger.info(
                "Discord RPC updated: details=%s state=%s account=%s "
                "total24h=%s session=%s total_acc=%s active_sessions=%s region=%s",
                details,
                state,
                selected_account_name or "-",
                format_duration(total_24h_seconds),
                format_duration(selected_session_seconds),
                format_duration(total_account_playtime_seconds),
                active_sessions_count,
                str(region).upper(),
            )
        except Exception as exc:
            now = time.time()
            # Throttle update errors so routine ticks do not flood the log.
            if now - self._last_update_error_log >= 60:
                self.logger.warning("Discord Rich Presence update failed: %s", exc)
                self._last_update_error_log = now
            self._connected = False
            self._rpc = None

    def close(self) -> None:
        """Clear and close RPC connection."""
        if not self._connected or self._rpc is None:
            return

        try:
            self._rpc.clear()
            self._rpc.close()
            self.logger.info("Discord Rich Presence disconnected")
        except Exception:
            pass
        finally:
            self._connected = False
            self._rpc = None


