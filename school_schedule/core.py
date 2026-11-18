"""Data model, schedule engine and persistence (no Qt dependencies)."""
from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_VERSION = 2
PALETTE = ["#4F8EF7", "#E5534B", "#3FB950", "#D29922", "#A371F7", "#F778BA",
           "#39C5CF", "#F0883E", "#8B949E", "#2EA043", "#BC8CFF", "#FF7B72"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ----------------------------------------------------------------- helpers
def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "school-schedule"


def hm(h: int, m: int = 0) -> int:
    return h * 60 + m


def fmt_min(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


def fmt_countdown(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m >= 1:
        return f"{m}m {s:02d}s" if m < 5 else f"{m} min"
    return f"{s}s"


def iso(d: date) -> str:
    return d.isoformat()


def parse_iso(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# --------------------------------------------------------------- templates
def _p(name, start, end, kind="class", slot=None):
    return {"name": name, "start": start, "end": end, "kind": kind, "slot": slot}


def make_periods(slots, class_len, pass_len, start, lunch_after=None, lunch_len=30):
    out, t = [], start
    for i in range(1, slots + 1):
        out.append(_p(f"Period {i}", t, t + class_len, "class", i))
        t += class_len
        if lunch_after == i:
            out.append(_p("Lunch", t, t + lunch_len, "lunch"))
            t += lunch_len
        elif i < slots:
            t += pass_len
    return out


TEMPLATES = {
    "wilton": "Wilton High School",
    "standard7": "Generic · 7 periods + lunch, same every day",
    "ab6": "Generic · 6 periods, A/B day rotation",
    "rot6": "Generic · 6 periods, 6-day rotating drop",
}


# Wilton High School bell times per rotation day (A-D), from schoology-wrapper's schedule.js.
# Each row is (block, start, end); positions in a day are the "class slots".
_WILTON = {
    "A": [("3", "08:20", "09:46"), ("1", "09:53", "11:19"), ("7", "11:26", "13:22"), ("5", "13:29", "14:55")],
    "B": [("2", "08:20", "09:03", "1/2"), ("2", "09:03", "09:46", "2/2"), ("4", "09:53", "11:19"),
          ("6", "11:26", "13:22"), ("8", "13:29", "14:55")],
    "C": [("1", "08:20", "09:39"), ("3", "09:46", "11:05"), ("ADV", "11:12", "11:37"),
          ("5", "11:44", "13:29"), ("7", "13:36", "14:55")],
    "D": [("4", "08:20", "09:46"), ("2", "09:53", "10:36", "1/2"), ("2", "10:36", "11:19", "2/2"),
          ("8", "11:26", "13:22"), ("6", "13:29", "14:55")],
}
# The known real week; the letter sequence runs backwards (B, A, D, C, B) and is irregular,
# so dates the user hasn't confirmed are extrapolated and can be overridden in Settings.
_WILTON_DAYMAP = {"2026-11-16": "B", "2026-11-17": "A", "2026-11-18": "D", "2026-11-19": "C", "2026-11-20": "B"}


def _t(s: str) -> int:
    h, m = s.split(":")
    return hm(int(h), int(m))


def _wilton() -> dict:
    letters = ["A", "B", "C", "D"]
    classes = [{"key": f"b{i}", "name": f"Block {i}", "colorHex": PALETTE[(i - 1) % len(PALETTE)]} for i in range(1, 9)]
    classes.append({"key": "adv", "name": "Advisory", "colorHex": "#8B949E"})
    key = lambda b: "adv" if b == "ADV" else f"b{b}"
    schedules, plans = {}, []
    for n, L in enumerate(letters, 1):
        rows = _WILTON[L]
        per = []
        for i, r in enumerate(rows, 1):
            q = _p(f"Block {r[0]}", _t(r[1]), _t(r[2]), "class", i)
            if len(r) > 3:
                q["part"] = r[3]
            per.append(q)
        schedules[f"regular:{n}"] = per
        plans.append({"day": n, "slots": [key(r[0]) for r in rows]})
    schedules["regular"] = [dict(p) for p in schedules["regular:1"]]
    schedules["short"], schedules["advisory"] = [], []
    school = {
        "name": "Wilton High School", "weekdays": [0, 1, 2, 3, 4], "rotationLength": 4, "rotationStep": -1,
        "dayLabels": letters, "anchorDate": "2026-11-16", "anchorDay": 2, "classPeriodCount": 5,
        "dayMap": {d: letters.index(l) + 1 for d, l in _WILTON_DAYMAP.items()}, "schedules": schedules,
    }
    return {"school": school, "classes": classes, "plans": plans}


def build_template(tid: str) -> dict:
    """Return {'school': patch, 'classes': [...], 'plans': [...]}."""
    if tid == "wilton":
        return _wilton()
    t = _build_generic(tid)
    t["school"].update(rotationStep=1, dayLabels=[], dayMap={})
    return t


def _build_generic(tid: str) -> dict:
    if tid == "ab6":
        n, rot = 6, 2
    elif tid == "rot6":
        n, rot = 6, 6
    else:
        n, rot = 7, 1
    classes = [{"key": f"c{i}", "name": f"Class {i}", "colorHex": PALETTE[(i - 1) % len(PALETTE)]}
               for i in range(1, (n * 2 if tid == "ab6" else n) + 1)]
    plans = []
    for day in range(1, rot + 1):
        if tid == "ab6":
            slots = [f"c{(day - 1) * 6 + i}" for i in range(1, 7)]
        elif tid == "rot6":
            slots = [f"c{(i + day - 2) % 6 + 1}" for i in range(1, 7)]
        else:
            slots = [f"c{i}" for i in range(1, n + 1)]
        plans.append({"day": day, "slots": slots})
    lunch_after = 4 if n == 7 else 3
    school = {
        "rotationLength": rot,
        "classPeriodCount": n,
        "schedules": {
            "regular": make_periods(n, 50 if n == 7 else 55, 5, hm(8), lunch_after, 40 if n == 7 else 35),
            "short": make_periods(n, 35, 5, hm(8), lunch_after, 25),
            "advisory": make_periods(n, 45, 5, hm(8, 30), lunch_after, 30),
        },
    }
    return {"school": school, "classes": classes, "plans": plans}


# ------------------------------------------------------------------ defaults
def default_data() -> dict:
    t = build_template("wilton")
    school = {
        "name": "My School",
        "weekdays": [0, 1, 2, 3, 4],
        "schoolDaysOnly": True,
        "anchorDate": iso(date.today()),
        "anchorDay": 1,
        "rotationStep": 1,
        "dayLabels": [],
        "dayMap": {},
        "daysOff": [],
        "yearEnd": None,
        "advisoryEnabled": False,
        "advisoryWeekday": 2,
        "shortDays": [],
        "lunch": {"enabled": False, "classSlot": 4, "waves": [], "wavePerDay": [0]},
    }
    school.update(t["school"])
    return {
        "version": DATA_VERSION,
        "setupDone": True,  # the default (Wilton) is fully auto-filled; no first-run wizard needed
        "school": school,
        "classes": t["classes"],
        "plans": t["plans"],
        "homework": [],
        "events": [],
        "reminders": {"enabled": True, "classStart": True, "leadMinutes": 5,
                      "morningOn": True, "morningHour": 7, "eveningOn": True,
                      "eveningHour": 19, "eveningBefore": True,
                      "lastMorning": None, "lastEvening": None},
        "appearance": {"themeID": "system", "customAccent": None, "showCountdownInMenuBar": True,
                       "pill": True, "pillCorner": "top-right"},
    }


def _merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for k, v in over.items():
            out[k] = _merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _migrate(raw: dict) -> dict:
    """v1 -> v2: the v1 default was a made-up placeholder schedule. If a saved file still holds that
    untouched placeholder, switch it to the (auto-filled) Wilton schedule and keep everything else.
    Anything the user customised is left alone."""
    if int(raw.get("version", 1)) >= 2:
        return raw
    sc = raw.get("school") or {}
    old = _build_generic("standard7")
    old_sched = old["school"]["schedules"]
    untouched = (
        sc.get("name", "My School") == "My School"
        and int(sc.get("rotationLength", 1)) == 1
        and all(sc.get("schedules", {}).get(k) == v for k, v in old_sched.items())
        and all(str(c.get("name", "")).startswith("Class ") for c in raw.get("classes", []))
    )
    out = copy.deepcopy(raw)
    out["version"] = DATA_VERSION
    if not untouched:
        return out
    w = _wilton()
    school = out.setdefault("school", {})
    school.update(w["school"])
    out["classes"], out["plans"] = w["classes"], w["plans"]
    for h in out.get("homework", []):  # old class keys c1..c7 -> Wilton blocks b1..b7
        k = h.get("classKey") or ""
        h["classKey"] = f"b{k[1:]}" if k.startswith("c") and k[1:].isdigit() and 1 <= int(k[1:]) <= 8 else None
    return out


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "data.json"
        self.data = self.load()

    def load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return default_data()
        try:
            migrated = _migrate(raw)
        except (KeyError, TypeError, ValueError):
            migrated = raw
        data = _merge(default_data(), migrated)
        if migrated is not raw:
            data["version"] = DATA_VERSION
            changed = migrated != {**raw, "version": DATA_VERSION}  # more than just the version bump
            try:
                if changed:  # keep the pre-migration file so nothing is ever lost
                    self.path.with_suffix(".v1.bak").write_text(json.dumps(raw, indent=2, sort_keys=True))
                self.data = data
                self.save()
            except OSError:
                pass
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)


# -------------------------------------------------------------------- engine
def is_day_off(data, d: date) -> bool:
    for r in data["school"]["daysOff"]:
        s, e = parse_iso(r.get("start")), parse_iso(r.get("end")) or parse_iso(r.get("start"))
        if s and e and s <= d <= e:
            return True
    ye = parse_iso(data["school"]["yearEnd"])
    return bool(ye and d > ye)


def is_school_day(data, d: date) -> bool:
    sc = data["school"]
    if sc["schoolDaysOnly"] and d.weekday() not in sc["weekdays"]:
        return False
    return not is_day_off(data, d)


def day_number(data, d: date) -> int:
    """Rotation day (1-based) for a school day."""
    sc = data["school"]
    length = max(1, int(sc["rotationLength"]))
    if length == 1:
        return 1
    dmap = sc.get("dayMap") or {}
    if iso(d) in dmap:
        return (int(dmap[iso(d)]) - 1) % length + 1
    anchors = [(parse_iso(k), int(v)) for k, v in dmap.items()]
    anchors.append((parse_iso(sc["anchorDate"]), int(sc["anchorDay"])))
    anchors = [a for a in anchors if a[0]]
    if not anchors:
        return 1
    before = [a for a in anchors if a[0] <= d]
    adate, aday = max(before) if before else min(anchors)
    count, cur = 0, adate
    if d >= adate:
        while cur < d and count < 5000:
            if is_school_day(data, cur):
                count += 1
            cur += timedelta(days=1)
    else:
        while cur > d and count > -5000:
            cur -= timedelta(days=1)
            if is_school_day(data, cur):
                count -= 1
    step = -1 if int(sc.get("rotationStep", 1)) < 0 else 1
    return (aday - 1 + step * count) % length + 1


def day_label(data, n: int) -> str:
    labels = data["school"].get("dayLabels") or []
    return labels[n - 1] if 0 < n <= len(labels) else str(n)


def day_type(data, d: date) -> str:
    sc = data["school"]
    if not is_school_day(data, d):
        return "off"
    if iso(d) in sc["shortDays"]:
        return "short"
    if sc["advisoryEnabled"] and d.weekday() == sc["advisoryWeekday"]:
        return "advisory"
    return "regular"


def class_by_key(data, key):
    for c in data["classes"]:
        if c["key"] == key:
            return c
    return None


def class_for_slot(data, d: date, slot: int):
    dn = day_number(data, d)
    plan = next((p for p in data["plans"] if p["day"] == dn), None)
    if plan and 0 < slot <= len(plan["slots"]):
        return class_by_key(data, plan["slots"][slot - 1])
    return None


def periods_for(data, d: date) -> list[dict]:
    dt = day_type(data, d)
    if dt == "off":
        return []
    sched = data["school"]["schedules"]
    dn = day_number(data, d)
    base = (sched.get(f"{dt}:{dn}") or sched.get(dt) or sched.get(f"regular:{dn}")
            or sched.get("regular") or [])
    lunch = data["school"]["lunch"]
    out = []
    waves_on = lunch["enabled"] and lunch["waves"]
    for p in sorted(base, key=lambda x: x["start"]):
        if waves_on and p["kind"] == "lunch":
            continue  # the wave window replaces the fixed lunch block
        q = dict(p, classKey=None, color=None)
        slot = p.get("slot")
        if p["kind"] == "class" and slot:
            c = class_for_slot(data, d, slot)
            if c:
                q.update(name=c["name"] + (f" ({p['part']})" if p.get("part") else ""),
                         classKey=c["key"], color=c["colorHex"])
            if lunch["enabled"] and lunch["waves"] and slot == lunch["classSlot"]:
                idx = lunch["wavePerDay"][(day_number(data, d) - 1) % len(lunch["wavePerDay"])] \
                    if lunch["wavePerDay"] else 0
                w = lunch["waves"][min(idx, len(lunch["waves"]) - 1)]
                q.update(name=q["name"] + f" (lunch wave {w['name']})", start=w["start"], end=w["end"])
        out.append(q)
    return sorted(out, key=lambda x: x["start"])


def next_school_day(data, d: date, limit=30) -> date | None:
    for i in range(1, limit + 1):
        n = d + timedelta(days=i)
        if is_school_day(data, n):
            return n
    return None


def next_class_date(data, class_key: str, frm: date) -> date | None:
    """First school day strictly after `frm` on which the class meets."""
    d = frm
    for _ in range(60):
        d = next_school_day(data, d)
        if d is None:
            return None
        if any(p["classKey"] == class_key for p in periods_for(data, d)):
            return d
    return None


def now_state(data, now: datetime) -> dict:
    d = now.date()
    secs = now.hour * 3600 + now.minute * 60 + now.second
    ps = periods_for(data, d)
    st = {"state": "off", "current": None, "next": None, "seconds": 0, "progress": 0.0,
          "periods": ps, "dayNumber": day_number(data, d) if ps else None,
          "dayLabel": day_label(data, day_number(data, d)) if ps else None,
          "dayType": day_type(data, d), "nextDate": None, "nextFirst": None}
    if ps:
        if secs < ps[0]["start"] * 60:
            st.update(state="before", next=ps[0], seconds=ps[0]["start"] * 60 - secs)
            return st
        for i, p in enumerate(ps):
            nxt = ps[i + 1] if i + 1 < len(ps) else None
            if p["start"] * 60 <= secs < p["end"] * 60:
                span = (p["end"] - p["start"]) * 60
                st.update(state="in", current=p, next=nxt, seconds=p["end"] * 60 - secs,
                          progress=(secs - p["start"] * 60) / span if span else 1.0)
                return st
            if nxt and p["end"] * 60 <= secs < nxt["start"] * 60:
                st.update(state="between", next=nxt, seconds=nxt["start"] * 60 - secs)
                return st
        st["state"] = "after"
    nd = next_school_day(data, d)
    if nd:
        nps = periods_for(data, nd)
        st.update(nextDate=nd, nextFirst=nps[0] if nps else None)
    return st


def events_on(data, d: date) -> list[dict]:
    out = [e for e in data["events"] if d.weekday() in e.get("weekdays", [])]
    return sorted(out, key=lambda e: e["start"])


def homework_sorted(data):
    return sorted(data["homework"], key=lambda h: (h["done"], h["due"] or "9999"))
