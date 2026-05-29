"""Automatic update checking and version management."""

import logging
import threading
import requests
from typing import Optional, Dict, Callable
from packaging import version as pkg_version

GITHUB_REPO = "xLordTime/wiz-q-launcher"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"


class UpdateChecker:
    """Check for new versions from GitHub releases."""

    def __init__(self, current_version: str, repo: str = GITHUB_REPO):
        """
        Initialize update checker.

        Args:
            current_version: Current app version (e.g., "5.1.0")
            repo: GitHub repository in owner/name format
        """
        self.logger = logging.getLogger("updater")
        # Validate current_version so _is_newer_version() never raises on our end.
        try:
            pkg_version.parse(current_version)
            self.current_version = current_version
        except Exception:
            self.logger.warning(
                "Invalid current_version %r — falling back to '0.0.0'",
                current_version,
            )
            self.current_version = "0.0.0"
        self.repo = repo
        self.github_api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        self.releases_page = f"https://github.com/{repo}/releases"

    # ------------------------------------------------------------------
    # Synchronous check
    # ------------------------------------------------------------------

    def check_for_updates(self) -> Optional[Dict]:
        """
        Check GitHub for the latest release synchronously.

        Returns:
            Dict with update info if a newer version is available, else None.
            Keys: new_version, download_url, release_page, changelog, published_at
        """
        try:
            response = requests.get(
                self.github_api_url,
                timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            release = response.json()

            new_version = release.get("tag_name", "").lstrip("v").strip()

            if new_version and self._is_newer_version(new_version):
                # Prefer .exe asset, fall back to release page URL
                download_url = None
                for asset in release.get("assets", []):
                    if asset["name"].lower().endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                release_page = release.get("html_url", self.releases_page)

                update_info = {
                    "new_version": new_version,
                    "current_version": self.current_version,
                    "download_url": download_url or release_page,
                    "release_page": release_page,
                    "changelog": release.get("body") or "No changelog provided.",
                    "published_at": release.get("published_at", ""),
                    "prerelease": release.get("prerelease", False),
                }
                self.logger.info("New version available: %s", new_version)
                return update_info

            self.logger.debug("Already on latest version (%s).", self.current_version)
            return None

        except requests.exceptions.ConnectionError:
            self.logger.debug("Update check skipped: no network connection.")
            return None
        except requests.exceptions.Timeout:
            self.logger.debug("Update check timed out.")
            return None
        except requests.exceptions.HTTPError as e:
            self.logger.debug("Update check HTTP error: %s", e)
            return None
        except Exception as e:
            self.logger.error("Update checker error: %s", e)
            return None

    # ------------------------------------------------------------------
    # Asynchronous (non-blocking) check
    # ------------------------------------------------------------------

    def check_for_updates_async(self, callback: Callable[[Optional[Dict]], None]) -> None:
        """
        Run update check in a background thread.

        Args:
            callback: Called with the result Dict (or None) when done.
                      Will be called from the background thread — UI code
                      must schedule any window updates safely.
        """
        def _worker() -> None:
            result = self.check_for_updates()
            try:
                callback(result)
            except Exception as exc:
                self.logger.error("Update callback error: %s", exc)

        thread = threading.Thread(target=_worker, name="update-check", daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_newer_version(self, new_version: str) -> bool:
        """Return True if new_version is strictly greater than current_version."""
        try:
            return pkg_version.parse(new_version) > pkg_version.parse(self.current_version)
        except Exception:
            return False

    def get_changelog(self, version: str) -> Optional[str]:
        """Fetch changelog for a specific release tag from GitHub."""
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/tags/v{version}"
            response = requests.get(url, timeout=8, headers={"Accept": "application/vnd.github+json"})
            response.raise_for_status()
            return response.json().get("body") or "No changelog available."
        except Exception as e:
            self.logger.warning("Failed to fetch changelog for %s: %s", version, e)
            return None

    @staticmethod
    def format_release_info(update_info: Dict) -> str:
        """Return a human-readable update announcement string."""
        pre = "  [Pre-release]\n" if update_info.get("prerelease") else ""
        pub = update_info.get("published_at", "")[:10]  # just the date
        changelog = (update_info.get("changelog") or "").strip()
        # Trim very long changelogs for popup readability
        if len(changelog) > 1200:
            changelog = changelog[:1200] + "\n\n... (see release page for full notes)"
        return (
            f"Version {update_info['new_version']} is available!\n"
            f"{pre}"
            f"Released: {pub}\n"
            f"You have: {update_info.get('current_version', '?')}\n"
            f"\n"
            f"{'─' * 48}\n"
            f"{changelog}\n"
            f"{'─' * 48}\n"
            f"\nDownload: {update_info['download_url']}"
        )
