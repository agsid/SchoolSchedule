"""School Schedule for Linux: system-tray app entry point."""
from __future__ import annotations

import ctypes.util
import os
import sys
from datetime import date, datetime, timedelta

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import core, notify, placement, session
from .ui import Pill, Popup, SettingsDialog, qss, resolve_theme

SOCKET = f"school-schedule-{os.getuid()}"


def make_icon(text: str, color: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(34 if len(text) <= 2 else 26)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.store = core.Store()
        self.data = self.store.data
        self.theme = self._theme()
        self.pinned = False
        self.popup = Popup(self)
        self.pill = Pill(self)
        self._settings = None
        self._leave = QTimer(self, singleShot=True, interval=450)
        self._leave.timeout.connect(self._maybe_hide)
        self._fired: set = set()

        self.tray = QSystemTrayIcon(self)
        menu = QMenu()
        for label, fn in (("Show panel", self.toggle_popup), ("Settings…", self.open_settings)):
            a = QAction(label, menu)
            a.triggered.connect(fn)
            menu.addAction(a)
        menu.addSeparator()
        q = QAction("Quit", menu)
        q.triggered.connect(app.quit)
        menu.addAction(q)
        self.tray.setContextMenu(menu)
        self._menu = menu
        self.tray.activated.connect(lambda r: self.toggle_popup() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.MiddleClick) else None)
        self._icon_key = None
        self.tick()
        self.tray.show()

        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.apply_theme()
        self._watch_system_theme()
        placement.setup(Pill.TITLE)
        self._sync_pill()

        # single-instance control channel: `school-schedule --toggle|--show|--settings`
        self.server = QLocalServer(self)
        QLocalServer.removeServer(SOCKET)
        self.server.listen(SOCKET)
        self.server.newConnection.connect(self._on_cmd)

        if not self.data["setupDone"]:
            QTimer.singleShot(300, self.open_settings)

    # ---- plumbing
    def _theme(self):
        return resolve_theme(self.data["appearance"], QApplication.palette())

    def apply_theme(self):
        self.theme = self._theme()
        self.app.setStyleSheet(qss(self.theme))
        self._icon_key = None
        self.pill.update()
        if self.popup.isVisible():
            self.popup.refresh(full=True)

    def _watch_system_theme(self):
        """Re-theme live when kdeglobals changes (Noctalia/KDE rewrite it on scheme changes)."""
        self._kde = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeglobals"
        self._fw = QFileSystemWatcher([str(self._kde)], self)
        self._debounce = QTimer(self, singleShot=True, interval=300)
        self._debounce.timeout.connect(self._system_theme_changed)
        self._fw.fileChanged.connect(lambda _: self._debounce.start())
        self.app.styleHints().colorSchemeChanged.connect(lambda _: self._debounce.start())

    def _system_theme_changed(self):
        if self._kde.exists() and str(self._kde) not in self._fw.files():
            self._fw.addPath(str(self._kde))  # file was replaced atomically
        if self.data["appearance"]["themeID"] == "system":
            self.apply_theme()

    def save(self):
        self.store.save()

    def _on_cmd(self):
        sock = self.server.nextPendingConnection()
        sock.waitForReadyRead(500)
        cmd = bytes(sock.readAll()).decode().strip()
        sock.disconnectFromServer()
        {"toggle": self.toggle_pin, "show": lambda: self.show_popup(pin=True), "settings": self.open_settings,
         "quit": self.app.quit, "ping": lambda: self.show_popup(pin=True)}.get(cmd, lambda: None)()

    # ---- windows
    def _corner(self):
        return self.data["appearance"]["pillCorner"]

    def show_popup(self, pin=False):
        if pin:
            self.pinned = True
        self._leave.stop()
        if not self.popup.isVisible():
            self.popup.show()
        for ms in (0, 60, 200, 500):  # compositors map windows asynchronously; re-place a few times
            QTimer.singleShot(ms, self._place_panel)
        if pin:
            self.popup.raise_()
            self.popup.activateWindow()

    def _place_panel(self):
        if self.popup.isVisible():
            placement.place_panel(self.popup, self.pill if self.pill.isVisible() else None, self._corner())

    def toggle_pin(self):
        """Click on the pill / tray icon / --toggle: pin the panel open, or close it."""
        if self.popup.isVisible() and self.pinned:
            self.popup.hide()
        else:
            self.show_popup(pin=True)

    toggle_popup = toggle_pin

    def hover(self, inside: bool):
        if inside:
            self._leave.stop()
            if not self.popup.isVisible():
                self.show_popup()
        else:
            self._leave.start()

    def _maybe_hide(self):
        if self.pinned or self.settings_open() or self.app.activePopupWidget() is not None:
            return
        if self.popup.hw_title.hasFocus() and self.popup.hw_title.text():
            return  # don't discard a half-typed homework item
        if self.popup.underMouse() or self.pill.underMouse():
            return
        self.popup.hide()

    def _sync_pill(self):
        on = bool(self.data["appearance"]["pill"]) and placement.supported()
        if on and not self.pill.isVisible():
            self.pill.show()
        elif not on and self.pill.isVisible():
            self.pill.hide()
        if on:
            for ms in (0, 80, 300, 900):
                QTimer.singleShot(ms, lambda: placement.place_pill(self.pill, self._corner()))

    def settings_open(self):
        return self._settings is not None and self._settings.isVisible()

    def open_settings(self):
        if self.settings_open():
            self._settings.raise_()
            self._settings.activateWindow()
            return
        self._settings = SettingsDialog(self)
        self._settings.saved.connect(self.reload)
        self._settings.show()

    def reload(self):
        self.apply_theme()
        self._icon_key = None
        self._sync_pill()
        self.tick()
        if self.popup.isVisible():
            self.popup.refresh(full=True)
            self._place_panel()

    # ---- per-second work
    def tick(self):
        now = datetime.now()
        st = core.now_state(self.data, now)
        self._update_tray(st)
        self._update_pill(st)
        if self.data["reminders"]["enabled"]:
            self._reminders(now, st)

    def _update_tray(self, st):
        accent = self.theme["accent"]
        show = self.data["appearance"]["showCountdownInMenuBar"]
        if st["state"] in ("in", "between", "before") and show:
            mins = -(-st["seconds"] // 60)
            text = str(mins) if mins < 100 else f"{mins // 60}h"
            tip = (f"{st['current']['name']} — {core.fmt_countdown(st['seconds'])} left" if st["state"] == "in"
                   else f"{st['next']['name']} starts in {core.fmt_countdown(st['seconds'])}")
        else:
            text = "S"
            tip = "School Schedule — no class right now" if st["state"] != "off" else "School Schedule — no school today"
        color = (st["current"] or {}).get("color") or accent if st["state"] == "in" else accent
        key = (text, color)
        if key != self._icon_key:
            self._icon_key = key
            self.tray.setIcon(make_icon(text, color))
        self.tray.setToolTip(tip)

    def _update_pill(self, st):
        if not self.pill.isVisible():
            return
        s, cur, nxt = st["state"], st["current"], st["next"]
        short = lambda n: n if len(n) <= 16 else n[:15] + "…"
        if s == "in":
            col = cur["color"] or self.theme["accent"]
            html = f"<span style='color:{col}'>●</span> {short(cur['name'])} · {core.fmt_countdown(st['seconds'])}"
        elif s in ("before", "between"):
            html = f"{short(nxt['name'])} in {core.fmt_countdown(st['seconds'])}"
        else:
            html = "School's out" if s == "after" else "No school today"
        self.pill.set_text(html)

    def _reminders(self, now: datetime, st):
        r, today, secs = self.data["reminders"], now.date(), now.hour * 3600 + now.minute * 60 + now.second
        if r["classStart"]:
            for p in st["periods"]:
                if p["kind"] != "class":
                    continue
                lead = r["leadMinutes"] * 60
                until = p["start"] * 60 - secs
                key = (today, p["start"])
                if 0 <= until <= lead and key not in self._fired:
                    self._fired.add(key)
                    mins = max(1, round(until / 60))
                    when = "now" if until < 30 else f"in {mins} min"
                    notify.send(f"{p['name']} starts {when}", f"{core.fmt_min(p['start'])} – {core.fmt_min(p['end'])}", self.tray)
        if r["morningOn"] and now.hour >= r["morningHour"] and r["lastMorning"] != core.iso(today) and st["periods"]:
            r["lastMorning"] = core.iso(today)
            due = [h for h in self.data["homework"] if not h["done"] and h["due"] == core.iso(today)]
            dn = f"Day {st['dayLabel']} · " if self.data["school"]["rotationLength"] > 1 else ""
            body = f"{dn}{st['dayType'].title()} schedule, first class {core.fmt_min(st['periods'][0]['start'])}."
            if due:
                body += f" Homework due today: {', '.join(h['title'] for h in due)}."
            notify.send("Good morning", body, self.tray)
            self.save()
        if r["eveningOn"] and now.hour >= r["eveningHour"] and r["lastEvening"] != core.iso(today):
            r["lastEvening"] = core.iso(today)
            nd = core.next_school_day(self.data, today)
            limit = core.iso(nd) if (r["eveningBefore"] and nd) else "9999"
            due = [h for h in self.data["homework"] if not h["done"] and h["due"] and h["due"] <= limit]
            if due:
                notify.send(f"{len(due)} homework item(s) pending", "\n".join(h["title"] for h in due[:5]), self.tray)
            self.save()


def send_command(cmd: str) -> bool:
    s = QLocalSocket()
    s.connectToServer(SOCKET)
    if not s.waitForConnected(300):
        return False
    s.write(cmd.encode())
    s.flush()
    s.waitForBytesWritten(300)
    s.disconnectFromServer()
    return True


def _maybe_prefer_xwayland(args) -> None:
    """Native Wayland gives clients no control over window position/stacking (GNOME).  Running
    through XWayland restores it, so the hover widget works.  Automatic on GNOME when the
    xcb Qt plugin can load; otherwise opt in with `--x11` or SCHOOL_SCHEDULE_X11=1."""
    if os.environ.get("QT_QPA_PLATFORM") or session.session_type() != "wayland":
        return
    forced = "x11" in args or os.environ.get("SCHOOL_SCHEDULE_X11") == "1"
    if os.environ.get("SCHOOL_SCHEDULE_X11") == "0":
        return
    auto = session.desktop() == "gnome" and os.environ.get("DISPLAY") and ctypes.util.find_library("xcb-cursor")
    if forced or auto:
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def main() -> int:
    args = [a.lstrip("-") for a in sys.argv[1:]]
    cmd = next((a for a in args if a in ("toggle", "show", "settings", "quit", "help", "h")), None)
    if cmd in ("help", "h"):
        print("usage: school-schedule [--toggle | --show | --settings | --quit] [--x11]")
        return 0
    _maybe_prefer_xwayland(args)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("School Schedule")
    app.setDesktopFileName("school-schedule")
    icon_file = Path(__file__).parent / "assets" / "school-schedule.svg"
    app.setWindowIcon(QIcon.fromTheme("school-schedule", QIcon(str(icon_file))))
    app.setQuitOnLastWindowClosed(False)
    if send_command(cmd or "ping"):
        return 0  # already running; command delivered
    if cmd == "quit":
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("note: no system tray host found; open the panel with `school-schedule --toggle` "
              f"({session.keybind_hint()})", file=sys.stderr)
    ctl = Controller(app)
    if cmd in ("show", "toggle"):
        ctl.show_popup(pin=True)
    elif cmd == "settings":
        ctl.open_settings()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
