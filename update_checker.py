"""Automatic update checking and version management."""

import logging
import requests
from typing import Optional, Dict
from packaging import version as pkg_version


class UpdateChecker:
    """Check for new versions from GitHub releases."""

    def __init__(self, current_version: str, repo: str = "oliwi/q-launcher"):
        """
        Initialize update checker.
        
        Args:
            current_version: Current app version (e.g., "0.2.0")
            repo: GitHub repository (owner/name)
        """
        self.logger = logging.getLogger("updater")
        self.current_version = current_version
        self.repo = repo
        self.github_api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    def check_for_updates(self) -> Optional[Dict]:
        """
        Check GitHub for latest release.
        
        Returns:
            Dict with update info if newer version available, None otherwise:
                {
                    "new_version": "0.3.0",
                    "download_url": "https://...",
                    "changelog": "Release notes...",
                    "published_at": "2026-02-15T10:00:00Z"
                }
        """
        try:
            response = requests.get(self.github_api_url, timeout=5)
            response.raise_for_status()
            release = response.json()
            
            new_version = release.get("tag_name", "").lstrip("v")
            
            # Compare versions
            if new_version and self._is_newer_version(new_version):
                download_url = None
                for asset in release.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                
                if not download_url:
                    # Fallback to release page
                    download_url = release.get("html_url")
                
                update_info = {
                    "new_version": new_version,
                    "download_url": download_url,
                    "changelog": release.get("body", "No changelog provided"),
                    "published_at": release.get("published_at"),
                }
                
                self.logger.info(f"New version available: {new_version}")
                return update_info
            
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.debug(f"Update check failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Update checker error: {e}")
            return None

    def _is_newer_version(self, new_version: str) -> bool:
        """
        Compare versions using semantic versioning.
        
        Args:
            new_version: Version string to compare (e.g., "0.3.0")
            
        Returns:
            True if new_version > current_version
        """
        try:
            current = pkg_version.parse(self.current_version)
            latest = pkg_version.parse(new_version)
            return latest > current
        except Exception:
            return False

    def get_changelog(self, version: str) -> Optional[str]:
        """
        Get changelog for specific version.
        
        Args:
            version: Version to get changelog for
            
        Returns:
            Changelog text or None
        """
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/tags/v{version}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            release = response.json()
            return release.get("body", "No changelog available")
        except Exception as e:
            self.logger.warning(f"Failed to fetch changelog for {version}: {e}")
            return None

    @staticmethod
    def format_release_info(update_info: Dict) -> str:
        """
        Format update info for display.
        
        Args:
            update_info: Update info from check_for_updates()
            
        Returns:
            Formatted string
        """
        return (
            f"New version available: {update_info['new_version']}\n\n"
            f"Changelog:\n{update_info['changelog']}\n\n"
            f"Download: {update_info['download_url']}"
        )
