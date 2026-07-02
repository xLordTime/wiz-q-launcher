"""Automatic update checking and version management."""

import logging
import os
import shutil
import subprocess
import sys
import threading
import requests
from pathlib import Path
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
            current_version: Current app version (e.g., "5.2.0")
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

    # ------------------------------------------------------------------
    # Self-update: download + in-place replace
    # ------------------------------------------------------------------

    def download_update_async(
        self,
        update_info: Dict,
        on_progress: Callable[[int], None],
        on_complete: Callable[[Path], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Download the update .exe in a background thread.

        Callbacks are invoked from the worker thread — callers must route
        UI updates through a thread-safe queue.

        Args:
            update_info:  The dict returned by check_for_updates().
            on_progress:  Called with integer 0-100 as bytes arrive.
            on_complete:  Called with the Path of the downloaded file.
            on_error:     Called with an error description string.
        """
        def _worker() -> None:
            url = update_info.get("download_url", "")
            new_version = str(update_info.get("new_version", "")).strip()
            if not url or not url.lower().endswith(".exe"):
                on_error("No .exe download URL found in this release.")
                return

            if getattr(sys, "frozen", False):
                dest_dir = Path(sys.executable).parent
            else:
                # Dev mode — put next to the project root
                dest_dir = Path(__file__).resolve().parent.parent

            if new_version:
                safe_ver = new_version.replace("/", "_").replace("\\", "_")
                dest_path = dest_dir / f"wiz-q-launcher_update_{safe_ver}.exe"
            else:
                dest_path = dest_dir / "wiz-q-launcher_update.exe"
            legacy_aliases = [
                dest_dir / "wiz-q-launcher_update.exe",
                dest_dir / "WizQLauncher_update.exe",
            ]

            try:
                response = requests.get(
                    url,
                    stream=True,
                    timeout=120,
                    headers={"Accept": "application/octet-stream"},
                )
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(dest_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                on_progress(int(downloaded * 100 / total))

                on_progress(100)

                for alias_path in legacy_aliases:
                    if alias_path == dest_path:
                        continue
                    try:
                        shutil.copy2(dest_path, alias_path)
                    except Exception as alias_exc:
                        self.logger.warning(
                            "Could not refresh legacy update alias %s: %s",
                            alias_path,
                            alias_exc,
                        )

                on_complete(dest_path)
                self.logger.info("Update downloaded to %s", dest_path)

            except Exception as exc:
                self.logger.error("Update download failed: %s", exc)
                try:
                    dest_path.unlink()
                except Exception:
                    pass
                on_error(str(exc))

        threading.Thread(target=_worker, name="update-download", daemon=True).start()

    @staticmethod
    def apply_update_on_restart(new_exe_path: Path) -> bool:
        """Write a relay .bat that swaps new_exe_path → current exe once this process exits.

        Launches the relay detached so it survives after the launcher closes,
        then the caller should call sys.exit().

        Only works when running as a compiled (PyInstaller-frozen) .exe.
        Returns True on success, False otherwise.
        """
        if not getattr(sys, "frozen", False):
            return False

        current_exe = Path(sys.executable)
        bat_path = current_exe.parent / "_update_relay.bat"
        pid = os.getpid()

        # The label must be alphanumeric — use the PID
        script = (
            "@echo off\n"
            "rem Wiz Q Launcher auto-updater relay — auto-deleted after use\n"
            f":wait{pid}\n"
            f"tasklist /fi \"PID eq {pid}\" 2>nul | findstr /i \"{pid}\" >nul\n"
            f"if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait{pid})\n"
            f"move /Y \"{new_exe_path}\" \"{current_exe}\"\n"
            f"start \"\" \"{current_exe}\"\n"
            "del \"%~f0\"\n"
        )

        try:
            bat_path.write_text(script, encoding="ascii")
            subprocess.Popen(
                ["cmd.exe", "/c", str(bat_path)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            return True
        except Exception as exc:
            logging.getLogger("updater").error("Failed to launch update relay: %s", exc)
            try:
                bat_path.unlink()
            except Exception:
                pass
            return False
