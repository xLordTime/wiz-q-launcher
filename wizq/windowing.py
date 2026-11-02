"""Physical-pixel layouts and durable, identity-checked game-window changes."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass

LAYOUTS = {
    "auto": "Automatisches Raster",
    "horizontal": "Nebeneinander",
    "vertical": "Untereinander",
    "2x2": "Raster 2 × 2",
    "grid": "Eigenes Raster",
    "main-left": "Hauptfenster links",
    "main-right": "Hauptfenster rechts",
    "main-top": "Hauptfenster oben",
    "cascade": "Überlappend / Kaskade",
    "fill": "Monitor füllen",
    "custom": "Eigene Positionen und Größen",
}
MODES = {
    "unchanged": "Rahmen beibehalten",
    "windowed": "Mit Rahmen · frei skalierbar",
    "borderless": "Rahmenlos",
}
SIZES = [
    (960, 540),
    (1024, 768),
    (1280, 720),
    (1280, 800),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (1920, 1200),
    (2560, 1080),
    (2560, 1440),
    (3440, 1440),
    (3840, 2160),
]


@dataclass(frozen=True)
class Monitor:
    id: str
    rect: tuple[int, int, int, int]
    work: tuple[int, int, int, int]
    primary: bool = False


def rectangle(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError("Fensterposition benötigt vier ganze Zahlen: X, Y, Breite, Höhe.")
    x, y, w, h = value
    if not (-131072 <= x <= 131072 and -131072 <= y <= 131072 and 64 <= w <= 32768 and 64 <= h <= 32768):
        raise ValueError("Ungültige Fenstermaße; mindestens 64 × 64 Pixel verwenden.")
    return [x, y, w, h]


def window_config(value, default_mode="unchanged"):
    if isinstance(value, list):
        value = {"rect": value}
    if not isinstance(value, dict):
        raise ValueError("Ungültige Fensterkonfiguration.")
    mode, kind, topmost = (
        value.get("mode", default_mode),
        value.get("size_kind", "outer"),
        value.get("topmost"),
    )
    if (
        mode not in MODES
        or kind not in ("outer", "client")
        or topmost is not None
        and type(topmost) is not bool
    ):
        raise ValueError("Ungültiger Fenstermodus, Größentyp oder Vordergrundwert.")
    return {"rect": rectangle(value.get("rect")), "mode": mode, "size_kind": kind, "topmost": topmost}


def overlap(a, b):
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
        0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    )


def nearest_monitor(rect, monitors):
    if not monitors:
        raise ValueError("Kein Bildschirm verfügbar.")
    x, y, w, h = rect
    return max(
        monitors,
        key=lambda m: (
            overlap(rect, m.rect),
            -((x + w / 2 - m.rect[0] - m.rect[2] / 2) ** 2 + (y + h / 2 - m.rect[1] - m.rect[3] / 2) ** 2),
        ),
    )


def fit_rect(rect, bounds):
    x, y, w, h = rectangle(rect)
    bx, by, bw, bh = bounds
    w, h = min(w, bw), min(h, bh)
    return [max(bx, min(x, bx + bw - w)), max(by, min(y, by + bh - h)), w, h]


def recover_rect(rect, monitors):
    rect = rectangle(rect)
    # Permit intentional windows spanning displays, but keep the top edge reachable.
    if any(
        m.rect[0] - 16 <= rect[0] < m.rect[0] + m.rect[2] - 32
        and m.rect[1] - 16 <= rect[1] < m.rect[1] + m.rect[3] - 32
        and overlap(rect, m.rect) >= 64 * 32
        for m in monitors
    ):
        return rect
    return fit_rect(rect, nearest_monitor(rect, monitors).work)


def tile_rects(bounds, count, layout="auto", gap=8, margin=8, columns=2, rows=2, main=65, aspect="free"):
    if count < 1:
        return []
    if layout not in LAYOUTS or layout == "custom":
        raise ValueError("Ungültige automatische Fensteranordnung.")
    x, y, w, h = bounds
    x, y, w, h = x + margin, y + margin, w - 2 * margin, h - 2 * margin
    if w < 64 or h < 64:
        raise ValueError("Rand ist zu groß für diesen Bildschirm.")
    if layout == "fill" or count == 1 and layout not in ("2x2", "grid"):
        result = [[x, y, w, h] for _ in range(count)]
    elif layout == "cascade":
        step = 32
        width, height = max(64, w * 3 // 4), max(64, h * 3 // 4)
        slots = max(1, min((w - width) // step, (h - height) // step) + 1)
        result = [[x + i % slots * step, y + i % slots * step, width, height] for i in range(count)]
    elif layout.startswith("main-"):
        main = max(30, min(85, main))
        if layout == "main-top":
            large = (h - gap) * main // 100
            result = [[x, y, w, large]] + tile_rects(
                [x, y + large + gap, w, h - large - gap], count - 1, "horizontal", gap, 0
            )
        else:
            large = (w - gap) * main // 100
            left = layout == "main-left"
            result = [[x if left else x + w - large, y, large, h]] + tile_rects(
                [x + large + gap if left else x, y, w - large - gap, h], count - 1, "vertical", gap, 0
            )
    else:
        if layout == "horizontal":
            columns, rows = count, 1
        elif layout == "vertical":
            columns, rows = 1, count
        elif layout == "auto":
            columns = min(count, max(1, math.ceil(math.sqrt(count * w / h / (16 / 9)))))
            rows = math.ceil(count / columns)
        else:
            columns, rows = (2, 2) if layout == "2x2" else (max(1, columns), max(1, rows))
            rows = max(rows, math.ceil(count / columns))
        available_w, available_h = w - gap * (columns - 1), h - gap * (rows - 1)
        result = []
        for i in range(count):
            col, row = i % columns, i // columns
            left, top = col * available_w // columns, row * available_h // rows
            right, bottom = (col + 1) * available_w // columns, (row + 1) * available_h // rows
            result.append([x + left + col * gap, y + top + row * gap, right - left, bottom - top])
    if aspect != "free":
        ratios = {"16:9": 16 / 9, "16:10": 1.6, "4:3": 4 / 3}
        ratio = ratios[aspect]
        for rect in result:
            old_w, old_h = rect[2:]
            rect[2], rect[3] = min(old_w, int(old_h * ratio)), min(old_h, int(old_w / ratio))
            rect[0] += (old_w - rect[2]) // 2
            rect[1] += (old_h - rect[3]) // 2
    try:
        return [rectangle(rect) for rect in result]
    except ValueError:
        raise ValueError(
            "Zu viele Fenster oder zu große Abstände für diese Anordnung. Automatisches Raster oder weitere Monitore wählen."
        ) from None


def arrange(monitors, instances, options):
    if not instances:
        return []
    target = options.get("monitor", "primary")
    primary = next((m for m in monitors if m.primary), monitors[0])
    chosen = monitors if target == "all" else [next((m for m in monitors if m.id == target), primary)]
    groups = {m.id: [] for m in chosen}
    for i, instance in enumerate(instances):
        groups[chosen[i % len(chosen)].id].append(instance)
    result = []
    for monitor in chosen:
        group = groups[monitor.id]
        rects = tile_rects(
            monitor.work if options.get("work_area", True) else monitor.rect,
            len(group),
            options.get("layout", "auto"),
            options.get("gap", 8),
            options.get("margin", 8),
            options.get("columns", 2),
            options.get("rows", 2),
            options.get("main", 65),
            options.get("aspect", "free"),
        )
        result.extend(
            {
                "entry": entry,
                "rect": rect,
                "mode": options.get("mode", "unchanged"),
                "topmost": options.get("topmost"),
                "size_kind": "outer",
            }
            for entry, rect in zip(group, rects)
        )
    # Monitor distribution must not reorder per-account profile slots.
    return sorted(result, key=lambda p: instances.index(p["entry"]))


def identity(instance):
    return f"{instance['pid']}:{instance['created']:.6f}:{instance['hwnd']}"


def preferences(store):
    from .settings import get

    options = {
        "layout": get(store, "window_layout"),
        "mode": get(store, "window_mode"),
        "monitor": "primary",
        "work_area": True,
        "gap": get(store, "window_gap"),
        "margin": get(store, "window_margin"),
        "columns": 2,
        "rows": 2,
        "main": 65,
        "aspect": "free",
        "topmost": None,
    }
    saved = store.get("window_arrangement", {})
    if isinstance(saved, dict):
        options.update({k: v for k, v in saved.items() if k in options})
    # The searchable settings page is authoritative for these shared values.
    options.update(
        layout=get(store, "window_layout"),
        mode=get(store, "window_mode"),
        gap=get(store, "window_gap"),
        margin=get(store, "window_margin"),
    )
    return options


class WindowManager:
    def __init__(self, store, api=None):
        self.store, self._api = store, api
        self.lock = threading.RLock()

    @property
    def api(self):
        if self._api is None:
            from .win32_windows import Win32Windows

            self._api = Win32Windows()
        return self._api

    def bind(self, instance, account_id):
        if account_id:
            links = self.store.get("window_account_links", {})
            links[identity(instance)] = account_id
            self.store.set("window_account_links", dict(list(links.items())[-256:]))

    def account_for(self, instance):
        return self.store.get("window_account_links", {}).get(identity(instance))

    def apply(self, plans):
        with self.lock:
            before, originals = [], self.store.get("window_originals", {})
            for plan in plans:
                instance = plan["entry"]["instance"]
                if not instance or not self.api.valid(instance):
                    raise ValueError(
                        "Ein gewählter Spielclient ist nicht mehr verfügbar. Fensterliste aktualisieren."
                    )
                rectangle(plan["rect"])
                if plan.get("mode", "unchanged") not in MODES or plan.get("size_kind", "outer") not in (
                    "outer",
                    "client",
                ):
                    raise ValueError("Ungültiger Fenstermodus oder Größentyp.")
                if plan.get("topmost") is not None and type(plan["topmost"]) is not bool:
                    raise ValueError("Ungültige Vordergrundoption.")
                snapshot = {"instance": instance, "state": self.api.snapshot(instance["hwnd"])}
                before.append(snapshot)
                originals.setdefault(identity(instance), snapshot)
            # Commit the recovery state BEFORE the first external window mutation.
            with self.store.transaction():
                self.store.set("window_originals", dict(list(originals.items())[-256:]))
                self.store.set("window_undo", before)
            changed = []
            try:
                for plan, previous in zip(plans, before):
                    instance = previous["instance"]
                    if not self.api.valid(instance):
                        raise ValueError("Der Spielclient wurde während der Anordnung beendet.")
                    changed.append(previous)
                    original_style = originals[identity(instance)]["state"]["style"]
                    self.api.apply(
                        instance["hwnd"],
                        plan["rect"],
                        plan.get("mode", "unchanged"),
                        plan.get("topmost"),
                        plan.get("size_kind", "outer"),
                        original_style,
                    )
            except Exception:
                for previous in reversed(changed):
                    if self.api.valid(previous["instance"]):
                        try:
                            self.api.restore(previous["instance"]["hwnd"], previous["state"])
                        except OSError:
                            pass
                raise
            return len(changed)

    def restore(self, instances=None, undo=False):
        with self.lock:
            snapshots = (
                self.store.get("window_undo", [])
                if undo
                else list(self.store.get("window_originals", {}).values())
            )
            keys = {identity(i) for i in instances} if instances is not None else None
            done = 0
            for saved in snapshots:
                instance = saved["instance"]
                if (keys is None or identity(instance) in keys) and self.api.valid(instance):
                    self.api.restore(instance["hwnd"], saved["state"])
                    done += 1
            return done

    def show(self, instance, action):
        if action not in ("minimize", "maximize", "restore"):
            raise ValueError("Unbekannte Fensteraktion.")
        with self.lock:
            if not self.api.valid(instance):
                raise ValueError("Dieser Spielclient ist nicht mehr verfügbar.")
            snapshot = {"instance": instance, "state": self.api.snapshot(instance["hwnd"])}
            originals = self.store.get("window_originals", {})
            originals.setdefault(identity(instance), snapshot)
            with self.store.transaction():
                self.store.set("window_originals", dict(list(originals.items())[-256:]))
                self.store.set("window_undo", [snapshot])
            try:
                self.api.show(instance["hwnd"], action)
            except OSError:
                if self.api.valid(instance):
                    self.api.restore(instance["hwnd"], snapshot["state"])
                raise

    def save_accounts(self, entries):
        saved = self.store.get("window_placements", {})
        count = 0
        for entry in entries:
            account = entry.get("account_id")
            if not account:
                continue
            instance = entry.get("instance")
            if instance:
                if not self.api.valid(instance):
                    continue
                state = self.api.snapshot(instance["hwnd"])
                config = {
                    "rect": state["rect"],
                    "mode": "borderless" if not state["style"] & 0x00C00000 else "windowed",
                    "topmost": state["topmost"],
                    "size_kind": "outer",
                }
            else:
                config = {k: entry[k] for k in ("rect", "mode", "topmost", "size_kind")}
                rectangle(config["rect"])
            saved[account] = window_config(config)
            count += 1
        self.store.set("window_placements", saved)
        return count

    def apply_saved(self, instance):
        self.bind(instance, instance.get("account_id"))
        config = self.store.get("window_placements", {}).get(instance.get("account_id"))
        if config is None:
            return False
        from .settings import get

        config = window_config(config, get(self.store, "window_mode"))
        config["rect"] = recover_rect(config["rect"], self.api.monitors())
        self.apply([{**config, "entry": {"instance": instance}}])
        return True
