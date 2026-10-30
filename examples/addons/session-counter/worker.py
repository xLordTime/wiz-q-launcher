"""Minimal stdlib-only worker. No core credentials are received."""
import json
import sys

count = 0
for line in sys.stdin:
    packet = json.loads(line)
    event = packet.get("event")
    if event == "host.stop":
        break
    if event == "session.started":
        count += 1
    if event in ("host.ready", "session.started"):
        print(json.dumps({"type": "status", "text": f"Session Counter: {count} starts this run"}), flush=True)
