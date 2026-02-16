"""Log file reader and viewer for UI integration."""

import logging
from pathlib import Path
from typing import List, Optional
from collections import deque


class LogViewer:
    """Read and serve log file contents for UI display."""

    def __init__(self, log_file: Path, max_lines: int = 500):
        """
        Initialize log viewer.
        
        Args:
            log_file: Path to log file
            max_lines: Maximum lines to keep in memory
        """
        self.logger = logging.getLogger("logviewer")
        self.log_file = Path(log_file)
        self.max_lines = max_lines
        self._line_cache: deque = deque(maxlen=max_lines)
        self._last_position = 0

    def get_latest_logs(self, num_lines: int = 100) -> List[str]:
        """
        Get latest N log lines.
        
        Args:
            num_lines: Number of lines to return
            
        Returns:
            List of log lines (newest last)
        """
        self._reload_from_file()
        
        lines = list(self._line_cache)
        return lines[-num_lines:] if len(lines) > num_lines else lines

    def get_all_logs(self) -> List[str]:
        """
        Get all cached log lines.
        
        Returns:
            List of all cached log lines
        """
        self._reload_from_file()
        return list(self._line_cache)

    def search_logs(self, query: str, case_sensitive: bool = False) -> List[str]:
        """
        Search log lines for query string.
        
        Args:
            query: Search query
            case_sensitive: Case-sensitive search
            
        Returns:
            List of matching log lines
        """
        self._reload_from_file()
        lines = list(self._line_cache)
        
        if case_sensitive:
            return [line for line in lines if query in line]
        else:
            query_lower = query.lower()
            return [line for line in lines if query_lower in line.lower()]

    def search_errors(self) -> List[str]:
        """
        Find all error and warning lines.
        
        Returns:
            List of lines containing ERROR or WARNING
        """
        self._reload_from_file()
        lines = list(self._line_cache)
        return [line for line in lines if "ERROR" in line or "WARNING" in line]

    def filter_by_level(self, level: str) -> List[str]:
        """
        Filter logs by severity level.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            
        Returns:
            List of lines with that level
        """
        self._reload_from_file()
        lines = list(self._line_cache)
        level_upper = level.upper()
        return [line for line in lines if f" {level_upper} " in line]

    def filter_by_module(self, module: str) -> List[str]:
        """
        Filter logs by module/logger name.
        
        Args:
            module: Module name to filter by
            
        Returns:
            List of lines from that module
        """
        self._reload_from_file()
        lines = list(self._line_cache)
        return [line for line in lines if module in line]

    def get_log_stats(self) -> dict:
        """
        Get statistics about logged events.
        
        Returns:
            Dict with log statistics
        """
        self._reload_from_file()
        lines = list(self._line_cache)
        
        stats = {
            "total_lines": len(lines),
            "debug_count": sum(1 for line in lines if " DEBUG " in line),
            "info_count": sum(1 for line in lines if " INFO " in line),
            "warning_count": sum(1 for line in lines if " WARNING " in line),
            "error_count": sum(1 for line in lines if " ERROR " in line),
        }
        
        return stats

    def _reload_from_file(self) -> None:
        """
        Reload new lines from log file since last read.
        Uses file position tracking to be efficient.
        """
        if not self.log_file.exists():
            self.logger.warning(f"Log file not found: {self.log_file}")
            return
        
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                # Seek to last known position
                f.seek(self._last_position)
                
                # Read new lines
                new_lines = f.readlines()
                self._last_position = f.tell()
                
                # Add to cache
                for line in new_lines:
                    self._line_cache.append(line.rstrip("\n"))
                    
        except Exception as e:
            self.logger.error(f"Error reading log file: {e}")

    def clear_cache(self) -> None:
        """Clear cached log lines."""
        self._line_cache.clear()
        self._last_position = 0
        self.logger.debug("Log cache cleared")

    def get_file_size(self) -> int:
        """
        Get log file size in bytes.
        
        Returns:
            File size or 0 if not found
        """
        if self.log_file.exists():
            return self.log_file.stat().st_size
        return 0

    def get_file_mtime(self) -> Optional[str]:
        """
        Get log file modification time.
        
        Returns:
            Formatted datetime or None
        """
        if self.log_file.exists():
            mtime = self.log_file.stat().st_mtime
            from datetime import datetime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        return None
