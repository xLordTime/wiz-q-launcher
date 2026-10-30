from __future__ import annotations

import time
import uuid


def duration(seconds):
    value = max(0, int(seconds))
    return f"{value // 3600}h {(value % 3600) // 60:02d}m"


class Sessions:
    def __init__(self, store, clock=time.monotonic, wall=time.time):
        self.store, self.clock, self.wall = store, clock, wall
        self.live = {}
        # Never credit the time spent offline after a crash.
        with store.transaction() as db:
            db.execute("UPDATE sessions SET ended=seen,reason='recovered' WHERE ended IS NULL")

    def start(self, pid, created, hwnd, region, account_id=None):
        identity = (int(pid), float(created))
        if identity in self.live:
            return self.live[identity]["id"]
        sid, now = str(uuid.uuid4()), self.wall()
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO sessions(id,account_id,region,pid,created,hwnd,started,seen) VALUES(?,?,?,?,?,?,?,?)",
                (sid, account_id, region, pid, created, hwnd, now, now),
            )
            if account_id:
                db.execute("UPDATE accounts SET last_used=? WHERE id=?", (now, account_id))
        self.live[identity] = {
            "id": sid,
            "tick": self.clock(),
            "seconds": 0.0,
            "hwnd": hwnd,
            "account_id": account_id,
            "region": region,
        }
        return sid

    def heartbeat(self, alive=None):
        wall, mono = self.wall(), self.clock()
        ended = []
        with self.store.transaction() as db:
            for identity, state in list(self.live.items()):
                delta = max(0.0, mono - state["tick"])
                # A long scheduling/suspend gap is not proof of client activity.
                valid = alive is None or alive(*identity)
                if delta <= 30 and valid:
                    state["seconds"] += delta
                    if delta > 0:
                        db.execute(
                            "INSERT INTO activity VALUES(?,?,?)", (str(uuid.uuid4()), wall - delta, wall)
                        )
                state["tick"] = mono
                db.execute(
                    "UPDATE sessions SET elapsed=?,seen=?,ended=?,reason=? WHERE id=?",
                    (
                        state["seconds"],
                        wall,
                        None if valid else wall,
                        None if valid else "process-ended",
                        state["id"],
                    ),
                )
                if not valid:
                    ended.append(dict(state))
                    self.live.pop(identity)
            db.execute("DELETE FROM activity WHERE ended<?", (wall - 172800,))
        return ended

    def assign(self, pid, created, account_id):
        state = self.live[(pid, created)]
        if state["account_id"]:
            raise ValueError("Sitzung ist bereits zugeordnet")
        with self.store.transaction() as db:
            db.execute("UPDATE sessions SET account_id=? WHERE id=?", (account_id, state["id"]))
        state["account_id"] = account_id

    def stop(self):
        self.heartbeat()
        with self.store.transaction() as db:
            for state in self.live.values():
                db.execute("UPDATE sessions SET ended=seen,reason='launcher-exit' WHERE id=?", (state["id"],))
        self.live.clear()

    def activity_24h(self):
        cutoff, now = self.wall() - 86400, self.wall()
        pairs = [
            (r["started"], r["ended"])
            for r in self.store.query("SELECT started,ended FROM activity WHERE ended>?", (cutoff,))
        ]
        merged = []
        for start, end in sorted((max(cutoff, a), min(now, b)) for a, b in pairs if b > cutoff):
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return sum(b - a for a, b in merged)
