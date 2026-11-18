"""Window placement across desktops.

Plain Wayland clients can't position their own windows, so each compositor gets a
backend:  hyprland (hyprctl) · sway (swaymsg) · kwin (KWin script over D-Bus) · qt (X11,
XWayland, offscreen: Qt's own move()).  Anything else (e.g. GNOME on native Wayland)
reports `supported() == False`; the app then skips the floating widget and the panel
opens wherever the compositor puts it (use the tray icon or `--toggle` there).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from . import session


def backend() -> str:
    if not (QGuiApplication.platformName() or "").startswith("wayland"):
        return "qt"
    d = session.desktop()
    if d == "hyprland" and shutil.which("hyprctl"):
        return "hyprland"
    if d == "sway" and shutil.which("swaymsg"):
        return "sway"
    if d == "kde":
        return "kwin"
    return "none"


def supported() -> bool:
    return backend() != "none"


# ----------------------------------------------------------- geometry helpers
def corner_xy(corner, area, w, h, margin=10):
    x0, y0, x1, y1 = area
    x = {"left": x0 + margin, "right": x1 - w - margin, "center": (x0 + x1 - w) / 2}[corner.split("-")[1]]
    y = y0 + margin if corner.startswith("top") else y1 - h - margin
    return x, y


def below_xy(corner, pill, area, w, h, gap=4):
    """Panel position next to the pill (x, y, pw, ph), clamped to the work area."""
    px, py, pw, ph = pill
    side = corner.split("-")[1]
    x = px if side == "left" else px + (pw - w) / 2 if side == "center" else px + pw - w
    y = py + ph + gap if corner.startswith("top") else py - h - gap
    x = min(max(x, area[0] + 4), area[2] - w - 4)
    y = min(max(y, area[1] + 4), area[3] - h - 4)
    return x, y


def _run(cmd, *args) -> str:
    try:
        return subprocess.run([cmd, *args], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------------------- Hyprland
def _hypr_json(*a):
    try:
        return json.loads(_run("hyprctl", *a, "-j") or "null")
    except ValueError:
        return None


def _hypr_client(title):
    for c in _hypr_json("clients") or []:
        if c.get("title") == title:
            return c
    return None


def _hypr_area():
    mons = _hypr_json("monitors") or []
    m = next((m for m in mons if m.get("focused")), mons[0] if mons else None)
    if not m:
        return None
    left, top, right, bottom = (m.get("reserved") or [0, 0, 0, 0])[:4]
    sc = m.get("scale", 1) or 1
    return (m["x"] + left, m["y"] + top, m["x"] + m["width"] / sc - right, m["y"] + m["height"] / sc - bottom)


def _hypr_dispatch(lua, legacy):
    """Hyprland >= 0.55 may use a Lua config and Lua dispatchers; older takes the classic form."""
    out = _run("hyprctl", "dispatch", lua)
    if "error" in out.lower() or "unknown" in out.lower():
        _run("hyprctl", "dispatch", *legacy.split(" ", 1))


def _hypr_move(title, x, y):
    c = _hypr_client(title)
    if not c:
        return
    a = c["address"]
    if not c.get("floating"):
        _hypr_dispatch(f"hl.dsp.window.float({{ action = 'enable', window = 'address:{a}' }})", f"setfloating address:{a}")
    _hypr_dispatch(f"hl.dsp.window.move({{ x = {int(x)}, y = {int(y)}, window = 'address:{a}' }})",
                   f"movewindowpixel exact {int(x)} {int(y)},address:{a}")


# ----------------------------------------------------------------------- Sway
def _sway_json(*a):
    try:
        return json.loads(_run("swaymsg", "-t", *a) or "null")
    except ValueError:
        return None


def _sway_area():
    f = next((w for w in _sway_json("get_workspaces") or [] if w.get("focused")), None)
    if not f:
        return None
    r = f["rect"]  # workspace rect already excludes bars
    return (r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])


def _sway_rect(title):
    def walk(n):
        if n.get("name") == title and n.get("pid"):
            r = n["rect"]
            return (r["x"], r["y"], r["width"], r["height"])
        for k in ("nodes", "floating_nodes"):
            for c in n.get(k, []):
                found = walk(c)
                if found:
                    return found
        return None
    tree = _sway_json("get_tree")
    return walk(tree) if tree else None


def _sway_crit(title):
    return '[title="^' + re.sub(r"[^A-Za-z0-9]", ".", title) + '$"]'


def _sway_move(title, x, y, sticky=False):
    cmds = ["floating enable", "border none"] + (["sticky enable"] if sticky else []) + \
           [f"move absolute position {int(x)} {int(y)}"]
    _run("swaymsg", f"{_sway_crit(title)} " + ", ".join(cmds))


# ------------------------------------------------------------------ KDE KWin
_KWIN_JS = """
(function () {
  var CAP = %(cap)s, REF = %(ref)s, CORNER = %(corner)s, W = %(w)d, H = %(h)d, M = 10, G = 4;
  var list = workspace.windowList ? workspace.windowList() : workspace.clientList();
  function find(t) { for (var i = 0; i < list.length; i++) if (list[i].caption === t) return list[i]; return null; }
  function geo(x) { return x.frameGeometry || x.geometry; }
  var w = find(CAP); if (!w) return;
  var area;
  try { area = workspace.clientArea(KWin.PlacementArea, w.output || w.screen, workspace.currentDesktop); }
  catch (e) { area = workspace.clientArea(KWin.PlacementArea, w); }
  var left = CORNER.indexOf("left") >= 0, center = CORNER.indexOf("center") >= 0, top = CORNER.indexOf("top") === 0;
  var ref = REF ? find(REF) : null, x, y;
  if (ref) {
    var r = geo(ref);
    x = left ? r.x : center ? r.x + (r.width - W) / 2 : r.x + r.width - W;
    y = top ? r.y + r.height + G : r.y - H - G;
  } else {
    x = left ? area.x + M : center ? area.x + (area.width - W) / 2 : area.x + area.width - W - M;
    y = top ? area.y + M : area.y + area.height - H - M;
  }
  x = Math.max(area.x + 4, Math.min(x, area.x + area.width - W - 4));
  y = Math.max(area.y + 4, Math.min(y, area.y + area.height - H - 4));
  var rect = { x: Math.round(x), y: Math.round(y), width: W, height: H };
  if ("frameGeometry" in w) w.frameGeometry = rect; else w.geometry = rect;
  w.keepAbove = true; w.skipTaskbar = true; w.skipPager = true; w.skipSwitcher = true; w.noBorder = true;
})();
"""


def kwin_script(caption, ref, corner, w, h) -> str:
    return _KWIN_JS % {"cap": json.dumps(caption), "ref": json.dumps(ref), "corner": json.dumps(corner),
                       "w": int(w), "h": int(h)}


def _kwin_run(js: str) -> None:
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
    except ImportError:
        return
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return
    name = f"school-schedule-{os.getpid()}"
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), name + ".js")
    with open(path, "w") as f:
        f.write(js)
    scripting = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", bus)
    scripting.call("unloadScript", name)
    r = scripting.call("loadScript", path, name)
    if r.type() != QDBusMessage.ReplyMessage or not r.arguments():
        return
    sid = int(r.arguments()[0])
    for obj in (f"/Scripting/Script{sid}", f"/{sid}"):  # Plasma 6 / Plasma 5
        s = QDBusInterface("org.kde.KWin", obj, "org.kde.kwin.Script", bus)
        if s.isValid():
            s.call("run")
            break
    QTimer.singleShot(1500, lambda: (scripting.call("unloadScript", name), os.path.exists(path) and os.remove(path)))


# ------------------------------------------------------------------- Qt (X11)
def _qt_area():
    g = QGuiApplication.primaryScreen().availableGeometry()
    return (g.left(), g.top(), g.left() + g.width(), g.top() + g.height())


# ------------------------------------------------------------------ public API
def setup(pill_title: str) -> None:
    """One-time compositor tweaks (Sway: keep the hover pill from stealing focus)."""
    if backend() == "sway":
        _run("swaymsg", f"no_focus {_sway_crit(pill_title)}")


def place_pill(pill, corner: str) -> None:
    be, title, w, h = backend(), pill.windowTitle(), pill.width(), pill.height()
    if be == "qt":
        x, y = corner_xy(corner, _qt_area(), w, h)
        pill.move(int(x), int(y))
    elif be == "hyprland":
        a = _hypr_area()
        if a:
            _hypr_move(title, *corner_xy(corner, a, w, h))
    elif be == "sway":
        a = _sway_area()
        if a:
            _sway_move(title, *corner_xy(corner, a, w, h), sticky=True)
    elif be == "kwin":
        _kwin_run(kwin_script(title, None, corner, w, h))


def place_panel(panel, pill, corner: str) -> None:
    """`pill` is the visible hover widget or None (then the panel goes to the corner)."""
    be, title, w, h = backend(), panel.windowTitle(), panel.width(), panel.height()
    pt = pill.windowTitle() if pill is not None else None
    if be == "qt":
        area = _qt_area()
        if pill is not None:
            g = pill.frameGeometry()
            x, y = below_xy(corner, (g.x(), g.y(), g.width(), g.height()), area, w, h)
        else:
            x, y = corner_xy(corner, area, w, h)
        panel.move(int(x), int(y))
    elif be == "hyprland":
        a = _hypr_area()
        c = _hypr_client(pt) if pt else None
        if a:
            _hypr_move(title, *(below_xy(corner, (*c["at"], *c["size"]), a, w, h) if c else corner_xy(corner, a, w, h)))
    elif be == "sway":
        a = _sway_area()
        r = _sway_rect(pt) if pt else None
        if a:
            _sway_move(title, *(below_xy(corner, r, a, w, h) if r else corner_xy(corner, a, w, h)))
    elif be == "kwin":
        _kwin_run(kwin_script(title, pt, corner, w, h))
