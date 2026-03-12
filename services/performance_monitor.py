"""Performance monitoring system for CPU/Memory/Process tracking."""

import logging
import psutil
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class PerformanceSnapshot:
    """Single point-in-time performance metrics."""
    timestamp: datetime
    cpu_percent: float  # System CPU usage (0-100%)
    memory_percent: float  # System memory usage (0-100%)
    process_memory_mb: float  # Wizard101 process memory (MB)


class PerformanceMonitor:
    """Monitor system and process performance metrics in real-time."""

    def __init__(self, max_history: int = 100):
        """
        Initialize performance monitor.
        
        Args:
            max_history: Maximum number of snapshots to keep in memory
        """
        self.logger = logging.getLogger("performance")
        self.max_history = max_history
        self.history: List[PerformanceSnapshot] = []
        self.wizard_pids: Dict[int, str] = {}  # {pid: account_name}

    def add_wizard_process(self, pid: int, account_name: str) -> None:
        """
        Register a Wizard101 process for monitoring.
        
        Args:
            pid: Process ID of Wizard101 instance
            account_name: Account name for reference
        """
        self.wizard_pids[pid] = account_name
        self.logger.debug(f"Monitoring PID {pid} for {account_name}")

    def remove_wizard_process(self, pid: int) -> None:
        """
        Unregister a Wizard101 process.
        
        Args:
            pid: Process ID to stop monitoring
        """
        if pid in self.wizard_pids:
            account = self.wizard_pids.pop(pid)
            self.logger.debug(f"Stopped monitoring PID {pid} ({account})")

    def take_snapshot(self) -> Optional[PerformanceSnapshot]:
        """
        Capture current system and process performance metrics.
        
        Returns:
            PerformanceSnapshot with current metrics, or None if error
        """
        try:
            # Get system-wide metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            
            # Get Wizard101 process memory (all instances combined)
            process_memory_mb = 0.0
            for pid in list(self.wizard_pids.keys()):
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        memory_info = proc.memory_info()
                        process_memory_mb += memory_info.rss / (1024 * 1024)  # Convert to MB
                    else:
                        self.remove_wizard_process(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.remove_wizard_process(pid)
            
            snapshot = PerformanceSnapshot(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                process_memory_mb=process_memory_mb
            )
            
            # Keep history limited
            self.history.append(snapshot)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            return snapshot
        except Exception as e:
            self.logger.warning(f"Performance snapshot failed: {e}")
            return None

    def get_average_metrics(self, last_n: int = 10) -> Dict[str, float]:
        """
        Calculate average metrics over last N snapshots.
        
        Args:
            last_n: Number of snapshots to average (default last 10)
            
        Returns:
            Dict with average cpu_percent and memory_percent
        """
        if not self.history:
            return {"cpu_percent": 0.0, "memory_percent": 0.0}
        
        recent = self.history[-last_n:] if len(self.history) >= last_n else self.history
        
        avg_cpu = sum(s.cpu_percent for s in recent) / len(recent)
        avg_memory = sum(s.memory_percent for s in recent) / len(recent)
        
        return {
            "cpu_percent": round(avg_cpu, 1),
            "memory_percent": round(avg_memory, 1),
            "wizard_memory_mb": round(sum(s.process_memory_mb for s in recent) / len(recent), 1)
        }

    def get_peak_metrics(self) -> Dict[str, float]:
        """
        Get peak (maximum) metrics from history.
        
        Returns:
            Dict with peak cpu_percent and memory_percent
        """
        if not self.history:
            return {"cpu_percent": 0.0, "memory_percent": 0.0}
        
        peak_cpu = max(s.cpu_percent for s in self.history)
        peak_memory = max(s.memory_percent for s in self.history)
        peak_wizard = max(s.process_memory_mb for s in self.history)
        
        return {
            "cpu_percent": round(peak_cpu, 1),
            "memory_percent": round(peak_memory, 1),
            "wizard_memory_mb": round(peak_wizard, 1)
        }

    def clear_history(self) -> None:
        """Clear all historical metrics."""
        self.history.clear()
        self.logger.debug("Performance history cleared")
