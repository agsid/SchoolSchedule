"""Qt widgets: the tray popup and the settings dialog."""
from __future__ import annotations

import configparser
import json
import os
import subprocess
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPalette
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
    QGraphicsOpacityEffect, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from . import autostart, core, placement, session

HELP_URL = "https://programsforyou.com/school-schedule#how-to-use"

THEMES = {
    "light":    {"bg": "#F5F5F7", "card": "#FFFFFF", "fg": "#1D1D1F", "muted": "#6E6E73", "accent": "#0A84FF"},
    "dark":     {"bg": "#1E1E20", "card": "#2A2A2D", "fg": "#F2F2F7", "muted": "#9A9AA0", "accent": "#0A84FF"},
    "midnight": {"bg": "#0B1020", "card": "#151C33", "fg": "#E6EAF5", "muted": "#8590B0", "accent": "#7C9CFF"},
    "forest":   {"bg": "#14201A", "card": "#1D2D25", "fg": "#E4F0E8", "muted": "#8DA699", "accent": "#4CC38A"},
}


def kde_colors():
    """Colors from ~/.config/kdeglobals (written by KDE, Noctalia, etc.), or None."""
    path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeglobals"
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None

    def c(sec, key):
        try:
            r, g, b = (int(x) for x in cp.get(sec, key).split(",")[:3])
            return f"#{r:02x}{g:02x}{b:02x}"
        except (configparser.Error, ValueError):
            return None

    t = {"bg": c("Colors:Window", "BackgroundNormal"), "card": c("Colors:View", "BackgroundNormal"),
         "fg": c("Colors:Window", "ForegroundNormal"), "muted": c("Colors:Window", "ForegroundInactive"),
         "accent": c("Colors:Selection", "BackgroundNormal"), "onaccent": c("Colors:Selection", "ForegroundNormal")}
    return t if all(t.values()) else None


def palette_colors(pal: QPalette) -> dict:
    return {"bg": pal.window().color().name(), "card": pal.base().color().name(),
            "fg": pal.windowText().color().name(), "muted": pal.color(QPalette.PlaceholderText).name(),
            "accent": pal.highlight().color().name(), "onaccent": pal.highlightedText().color().name()}


GNOME_ACCENTS = {"blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a", "yellow": "#c88800", "orange": "#ed5b00",
                 "red": "#e62d42", "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396"}


def gnome_accent():
    if not session.have("gsettings"):
        return None
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
                             capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return GNOME_ACCENTS.get(out.strip().strip("'"))


def resolve_theme(appearance: dict, pal: QPalette) -> dict:
    tid = appearance.get("themeID", "system")
    if tid == "system":
        gnome = session.desktop() == "gnome"
        t = (None if gnome else kde_colors()) or palette_colors(pal)
        if gnome and (acc := gnome_accent()):
            t["accent"] = acc
    else:
        t = dict(THEMES.get(tid, THEMES["light"]))
        t["onaccent"] = "#ffffff"
    if appearance.get("customAccent"):
        t["accent"] = appearance["customAccent"]
    return t


def tint(hexc: str, a: float) -> str:
    """CSS rgba() for QSS. (8-digit hex means #AARRGGBB in Qt, which is easy to get wrong.)"""
    c = QColor(hexc)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


def qtint(hexc: str, a: float) -> QColor:
    c = QColor(hexc)
    c.setAlphaF(a)
    return c


def _chevron(color: str):
    """A small down-chevron SVG in `color` (cached on disk) for combo/date drop-downs."""
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "school-schedule"
    p = d / f"chevron-{color.lstrip('#')}.svg"
    try:
        if not p.exists():
            d.mkdir(parents=True, exist_ok=True)
            p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                         f'<path d="M2 4.2l4 4 4-4" fill="none" stroke="{color}" stroke-width="1.6" '
                         'stroke-linecap="round" stroke-linejoin="round"/></svg>')
        return p.as_posix()
    except OSError:
        return None


def qss(t: dict) -> str:
    chev = _chevron(t["muted"])
    arrow = (f"QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({chev}); width: 12px; height: 12px; }}"
             if chev else "")
    bg, card, fg, mu, ac, on = t["bg"], t["card"], t["fg"], t["muted"], t["accent"], t["onaccent"]
    return f"""
    * {{ color: {fg}; font-size: 13px; }}
    QDialog {{ background: {bg}; }}
    QWidget#panel {{ background: {bg}; border: 1px solid {tint(mu, .35)}; border-radius: 18px; }}
    QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollArea {{ border: none; }}
    QLabel {{ background: transparent; }}
    QLabel#muted {{ color: {mu}; }}
    QLabel#title {{ font-size: 15px; font-weight: 600; }}
    QLabel#pagetitle {{ font-size: 20px; font-weight: 700; }}
    QLabel#big {{ font-size: 22px; font-weight: 700; }}
    QLabel#count {{ font-size: 26px; font-weight: 700; color: {ac}; }}
    QLabel#chip {{ background: {tint(ac, .18)}; color: {ac}; border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}
    QLabel#chipwarn {{ background: {tint('#E5534B', .18)}; color: #E5534B; border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}
    QLabel#chipmuted {{ background: {tint(mu, .18)}; color: {mu}; border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}
    QFrame#card {{ background: {card}; border-radius: 16px; }}
    QFrame#row {{ background: transparent; border-radius: 12px; }}
    QFrame#row[now="true"] {{ background: {tint(ac, .16)}; }}
    QFrame#segbar {{ background: {tint(mu, .16)}; border-radius: 12px; }}
    QPushButton {{ background: {card}; border: 1px solid {tint(mu, .30)}; border-radius: 9px; padding: 6px 14px; }}
    QPushButton:hover {{ border-color: {ac}; }}
    QPushButton:pressed {{ background: {tint(ac, .20)}; }}
    QPushButton#accent {{ background: {ac}; color: {on}; border: none; font-weight: 600; }}
    QPushButton#accent:hover {{ background: {tint(ac, .85)}; }}
    QPushButton#flat {{ background: transparent; border: none; color: {mu}; padding: 4px 9px; }}
    QPushButton#flat:hover {{ background: {tint(mu, .22)}; color: {fg}; }}
    QPushButton#seg {{ background: transparent; border: none; border-radius: 9px; padding: 6px 14px; color: {mu}; }}
    QPushButton#seg:checked {{ background: {card}; color: {fg}; font-weight: 600; }}
    QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{ background: {card}; border: 1px solid {tint(mu, .28)}; border-radius: 10px; padding: 5px 10px; selection-background-color: {ac}; selection-color: {on}; }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {{ border-color: {ac}; }}
    QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
    {arrow}
    QSpinBox::up-button, QSpinBox::down-button, QTimeEdit::up-button, QTimeEdit::down-button {{ width: 0; border: none; }}
    QComboBox QAbstractItemView {{ background: {card}; border: 1px solid {tint(mu, .3)}; selection-background-color: {ac}; selection-color: {on}; outline: none; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 2px solid {tint(mu, .7)}; background: transparent; }}
    QCheckBox::indicator:hover {{ border-color: {ac}; }}
    QCheckBox::indicator:checked {{ background: {ac}; border-color: {ac}; }}
    QListWidget, QTableWidget {{ background: {card}; border: none; border-radius: 12px; gridline-color: {tint(mu, .12)}; outline: none; }}
    QListWidget#nav {{ background: transparent; }}
    QListWidget#nav::item {{ padding: 9px 14px; border-radius: 10px; margin: 2px 0; color: {mu}; }}
    QListWidget#nav::item:selected {{ background: {tint(ac, .18)}; color: {ac}; font-weight: 600; }}
    QListWidget#nav::item:hover:!selected {{ background: {tint(mu, .12)}; }}
    QHeaderView::section {{ background: transparent; color: {mu}; border: none; padding: 7px; font-weight: 600; }}
    QTableWidget::item:selected {{ background: {tint(ac, .20)}; color: {fg}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; padding: 7px 14px; color: {mu}; }}
    QTabBar::tab:selected {{ color: {ac}; border-bottom: 2px solid {ac}; }}
    QProgressBar {{ background: {tint(mu, .22)}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
    QProgressBar::chunk {{ background: {ac}; border-radius: 4px; }}
    QGroupBox {{ background: {tint(mu, .07)}; border: none; border-radius: 14px; margin-top: 18px; padding: 14px 10px 10px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; top: 2px; color: {mu}; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {tint(mu, .40)}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}
    QScrollBar:horizontal {{ height: 9px; background: transparent; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {tint(mu, .40)}; border-radius: 4px; min-width: 28px; }}
    QToolTip {{ background: {card}; color: {fg}; border: 1px solid {tint(mu, .4)}; padding: 4px 8px; }}
    QMenu {{ background: {card}; border: 1px solid {tint(mu, .3)}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {tint(ac, .25)}; }}
    """


def dot(color):
    return f"<span style='color:{color or '#8B949E'}'>●</span>"


def hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f


# =========================================================== popup window
def _clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            w = it.widget()
            w.hide()           # deleteLater() alone leaves the old widget painted until the next loop turn
            w.setParent(None)
            w.deleteLater()
        elif it.layout():
            _clear(it.layout())


class NowCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(4)
        self.title = QLabel("", objectName="big")
        self.sub = QLabel("", objectName="muted")
        self.count = QLabel("", objectName="count")
        self.bar = QProgressBar(textVisible=False)
        self.bar.setRange(0, 1000)
        self.nxt = QLabel("", objectName="muted")
        self.title.setWordWrap(True)
        for w in (self.title, self.sub):
            lay.addWidget(w)
        lay.addSpacing(6)
        lay.addWidget(self.count)
        lay.addSpacing(4)
        lay.addWidget(self.bar)
        lay.addSpacing(6)
        lay.addWidget(self.nxt)

    def update_state(self, st: dict):
        s, cur, nxt = st["state"], st["current"], st["next"]
        self.bar.setVisible(s == "in")
        if s == "in":
            self.title.setText(f"{dot(cur['color'])}  {cur['name']}")
            self.sub.setText(f"{core.fmt_min(cur['start'])} – {core.fmt_min(cur['end'])}")
            self.count.setText(core.fmt_countdown(st["seconds"]) + " left")
            self.bar.setValue(int(st["progress"] * 1000))
        elif s in ("before", "between"):
            self.title.setText("Before school" if s == "before" else "Passing period")
            self.sub.setText("First class starts in" if s == "before" else f"{nxt['name']} starts in")
            self.count.setText(core.fmt_countdown(st["seconds"]))
        elif s == "after":
            self.title.setText("School's out")
            self.sub.setText("Nice work today")
            self.count.setText("")
        else:
            self.title.setText("No school today")
            self.sub.setText("")
            self.count.setText("")
        self.count.setVisible(bool(self.count.text()))
        self.sub.setVisible(bool(self.sub.text()))
        if s in ("in", "before") and nxt:
            self.nxt.setText(f"Next · {nxt['name']} at {core.fmt_min(nxt['start'])}")
        elif s == "between" and nxt:
            self.nxt.setText(f"{core.fmt_min(nxt['start'])} – {core.fmt_min(nxt['end'])}")
        elif s in ("after", "off") and st["nextDate"]:
            nd, f = st["nextDate"], st["nextFirst"]
            when = "tomorrow" if (nd - date.today()).days == 1 else nd.strftime("%A")
            self.nxt.setText(f"Next school day · {when}" + (f", first class {core.fmt_min(f['start'])}" if f else ""))
        else:
            self.nxt.setText("")
        self.nxt.setVisible(bool(self.nxt.text()))


class Popup(QWidget):
    W, H = 392, 620

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle("School Schedule")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QWidget(objectName="panel")
        outer.addWidget(self.panel)
        root = QVBoxLayout(self.panel)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        tb = QVBoxLayout()
        tb.setSpacing(3)
        self.school = QLabel("", objectName="title")
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        self.date_lbl = QLabel("", objectName="muted")
        tb.addWidget(self.school)
        tb.addLayout(self.chips)
        head.addLayout(tb, 1)
        gear = QPushButton("⚙", objectName="flat")
        gear.setToolTip("Settings")
        gear.clicked.connect(ctl.open_settings)
        close = QPushButton("✕", objectName="flat")
        close.setToolTip("Close")
        close.clicked.connect(self.hide)
        head.addWidget(gear, 0, Qt.AlignTop)
        head.addWidget(close, 0, Qt.AlignTop)
        root.addLayout(head)

        self.now = NowCard()
        root.addWidget(self.now)

        # segmented control
        seg = QFrame(objectName="segbar")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(4)
        self.b_today = QPushButton("Today", objectName="seg", checkable=True, checked=True, autoExclusive=True)
        self.b_hw = QPushButton("Homework", objectName="seg", checkable=True, autoExclusive=True)
        sl.addWidget(self.b_today, 1)
        sl.addWidget(self.b_hw, 1)
        root.addWidget(seg)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.b_today.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.b_hw.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        # ---- today page
        self.today_body = QWidget(objectName="page")
        self.today_lay = QVBoxLayout(self.today_body)
        self.today_lay.setContentsMargins(0, 0, 4, 0)
        self.today_lay.setSpacing(2)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(self.today_body)
        self.stack.addWidget(sa)

        # ---- homework page
        hw = QWidget(objectName="page")
        hl = QVBoxLayout(hw)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        self.hw_body = QWidget(objectName="page")
        self.hw_lay = QVBoxLayout(self.hw_body)
        self.hw_lay.setContentsMargins(0, 0, 4, 0)
        self.hw_lay.setSpacing(2)
        hsa = QScrollArea()
        hsa.setWidgetResizable(True)
        hsa.setWidget(self.hw_body)
        hl.addWidget(hsa, 1)
        self.hw_title = QLineEdit(placeholderText="Add homework…")
        self.hw_class = QComboBox()
        self.hw_when = QComboBox()
        self.hw_when.addItems(["Next class", "Tomorrow", "Pick date…"])
        self.hw_date = QDateEdit(QDate.currentDate().addDays(1), calendarPopup=True)
        self.hw_date.setVisible(False)
        self.hw_when.currentIndexChanged.connect(lambda i: self.hw_date.setVisible(i == 2))
        add = QPushButton("Add", objectName="accent")
        add.clicked.connect(self._hw_add)
        self.hw_title.returnPressed.connect(self._hw_add)
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        r1.addWidget(self.hw_title, 1)
        r1.addWidget(add)
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(self.hw_class, 1)
        r2.addWidget(self.hw_when, 1)
        r2.addWidget(self.hw_date)
        clear = QPushButton("Clear done", objectName="flat")
        clear.clicked.connect(self._hw_clear)
        hl.addLayout(r1)
        hl.addLayout(r2)
        hl.addWidget(clear, 0, Qt.AlignRight)
        self.stack.addWidget(hw)

        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.refresh)

    # ---- lifecycle
    def showEvent(self, e):
        self.refresh(full=True)
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.ctl.pinned = False
        self.timer.stop()
        super().hideEvent(e)

    def enterEvent(self, e):
        self.ctl.hover(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.ctl.hover(False)
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(e)

    # ---- content
    def refresh(self, full=False):
        data = self.ctl.data
        st = core.now_state(data, datetime.now())
        self.now.update_state(st)
        d = date.today()
        sig = (st["state"], st["current"]["start"] if st["current"] else None, len(st["periods"]), d)
        if full or sig != getattr(self, "_sig", None):
            self._sig = sig
            self._fill_header(st, d)
            self._fill_today(st)
        if full:
            self._fill_homework()

    def _fill_header(self, st, d):
        data = self.ctl.data
        self.school.setText(data["school"]["name"])
        _clear(self.chips)
        chips = [(f"{d.strftime('%a, %b')} {d.day}", "chipmuted")]
        if st["dayLabel"] and data["school"]["rotationLength"] > 1:
            chips.append((f"Day {st['dayLabel']}", "chip"))
        if st["dayType"] not in ("regular", "off"):
            chips.append((st["dayType"].title(), "chip"))
        for text, name in chips:
            self.chips.addWidget(QLabel(text, objectName=name))
        self.chips.addStretch(1)

    def _row(self, title, sub, color, state, badge=None, right=None):
        f = QFrame(objectName="row")
        f.setProperty("now", state == "now")
        h = QHBoxLayout(f)
        h.setContentsMargins(10, 8, 12, 8)
        h.setSpacing(12)
        bar = QFrame()
        bar.setFixedSize(4, 32)
        bar.setStyleSheet(f"background:{color or self.ctl.theme['muted']}; border-radius:2px;")
        box = QVBoxLayout()
        box.setSpacing(1)
        t = QLabel(title)
        if state == "now":
            fnt = t.font()
            fnt.setBold(True)
            t.setFont(fnt)
        box.addWidget(t)
        box.addWidget(QLabel(sub, objectName="muted"))
        h.addWidget(bar)
        h.addLayout(box, 1)
        if badge:
            h.addWidget(QLabel(badge, objectName="chip"))
        if right:
            h.addWidget(QLabel(right, objectName="muted"))
        if state == "past":
            eff = QGraphicsOpacityEffect(f)
            eff.setOpacity(0.45)
            f.setGraphicsEffect(eff)
        return f

    def _fill_today(self, st):
        _clear(self.today_lay)
        cur, nxt = st["current"], st["next"]
        for p in st["periods"]:
            if cur and cur["start"] == p["start"]:
                state, badge = "now", "Now"
            elif st["state"] in ("after",) or (cur and p["end"] <= cur["start"]) or \
                    (not cur and nxt and p["end"] <= nxt["start"]):
                state, badge = "past", None
            elif nxt and nxt["start"] == p["start"]:
                state, badge = "next", "Next"
            else:
                state, badge = "future", None
            self.today_lay.addWidget(self._row(
                p["name"], f"{core.fmt_min(p['start'])} – {core.fmt_min(p['end'])}",
                p["color"], state, badge, f"{p['end'] - p['start']} min"))
        evs = core.events_on(self.ctl.data, date.today())
        if evs:
            hdr = QLabel("AFTER SCHOOL", objectName="muted")
            hdr.setContentsMargins(10, 12, 0, 4)
            self.today_lay.addWidget(hdr)
            for e in evs:
                loc = f" · {e['location']}" if e.get("location") else ""
                self.today_lay.addWidget(self._row(
                    e["title"], f"{core.fmt_min(e['start'])} – {core.fmt_min(e['end'])}{loc}",
                    self.ctl.theme["accent"], "future"))
        if not st["periods"] and not evs:
            lbl = QLabel("Nothing scheduled today.", objectName="muted", alignment=Qt.AlignCenter)
            lbl.setContentsMargins(0, 30, 0, 0)
            self.today_lay.addWidget(lbl)
        self.today_lay.addStretch(1)

    def _fill_homework(self):
        data = self.ctl.data
        self.hw_class.blockSignals(True)
        cur = self.hw_class.currentData()
        self.hw_class.clear()
        self.hw_class.addItem("No class", None)
        for c in data["classes"]:
            self.hw_class.addItem(c["name"], c["key"])
        self.hw_class.setCurrentIndex(max(self.hw_class.findData(cur), 0))
        self.hw_class.blockSignals(False)

        _clear(self.hw_lay)
        today = date.today()
        items = core.homework_sorted(data)
        n_open = sum(1 for h in items if not h["done"])
        self.b_hw.setText(f"Homework ({n_open})" if n_open else "Homework")
        for h in items:
            c = core.class_by_key(data, h.get("classKey"))
            due = core.parse_iso(h["due"])
            chip, chip_name = None, "chipmuted"
            if due:
                delta = (due - today).days
                if delta < 0:
                    chip, chip_name = "Overdue", "chipwarn"
                elif delta == 0:
                    chip, chip_name = "Today", "chip"
                elif delta == 1:
                    chip, chip_name = "Tomorrow", "chip"
                else:
                    chip = f"{due.strftime('%a %b')} {due.day}"
            f = QFrame(objectName="row")
            hb = QHBoxLayout(f)
            hb.setContentsMargins(10, 7, 6, 7)
            hb.setSpacing(10)
            cb = QCheckBox()
            cb.setChecked(h["done"])
            cb.toggled.connect(lambda on, hid=h["id"]: self._hw_toggled(hid, on))
            box = QVBoxLayout()
            box.setSpacing(1)
            t = QLabel(h["title"])
            t.setWordWrap(True)
            if h["done"]:
                fnt = t.font()
                fnt.setStrikeOut(True)
                t.setFont(fnt)
            box.addWidget(t)
            if c:
                box.addWidget(QLabel(dot(c["colorHex"]) + " " + c["name"], objectName="muted"))
            hb.addWidget(cb)
            hb.addLayout(box, 1)
            if chip and not h["done"]:
                hb.addWidget(QLabel(chip, objectName=chip_name))
            rm = QPushButton("✕", objectName="flat")
            rm.setToolTip("Delete")
            rm.clicked.connect(lambda _=False, hid=h["id"]: self._hw_delete(hid))
            hb.addWidget(rm)
            if h["done"]:
                eff = QGraphicsOpacityEffect(f)
                eff.setOpacity(0.5)
                f.setGraphicsEffect(eff)
            self.hw_lay.addWidget(f)
        if not items:
            lbl = QLabel("No homework. Enjoy it while it lasts.", objectName="muted", alignment=Qt.AlignCenter)
            lbl.setContentsMargins(0, 30, 0, 0)
            self.hw_lay.addWidget(lbl)
        self.hw_lay.addStretch(1)

    def _hw_toggled(self, hid, on):
        for h in self.ctl.data["homework"]:
            if h["id"] == hid:
                h["done"] = on
        self.ctl.save()
        QTimer.singleShot(0, self._fill_homework)

    def _hw_delete(self, hid):
        self.ctl.data["homework"] = [h for h in self.ctl.data["homework"] if h["id"] != hid]
        self.ctl.save()
        QTimer.singleShot(0, self._fill_homework)

    def _hw_add(self):
        title = self.hw_title.text().strip()
        if not title:
            return
        key = self.hw_class.currentData()
        mode = self.hw_when.currentIndex()
        today = date.today()
        if mode == 0 and key:
            due = core.next_class_date(self.ctl.data, key, today)
        elif mode == 2:
            due = self.hw_date.date().toPython()
        else:
            due = core.next_school_day(self.ctl.data, today) or today + timedelta(days=1)
        self.ctl.data["homework"].append({"id": core.new_id(), "title": title, "classKey": key,
                                          "due": core.iso(due) if due else None, "done": False})
        self.hw_title.clear()
        self.ctl.save()
        self._fill_homework()

    def _hw_clear(self):
        self.ctl.data["homework"] = [h for h in self.ctl.data["homework"] if not h["done"]]
        self.ctl.save()
        self._fill_homework()


class Pill(QWidget):
    """Small always-on-top widget; hovering it opens the panel."""
    TITLE = "School Schedule Pill"
    SIZE = (200, 32)

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("pill")
        self.setWindowTitle(self.TITLE)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(*self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        self.label = QLabel("", alignment=Qt.AlignCenter)
        lay.addWidget(self.label)

    def set_text(self, html: str):
        if html != self.label.text():
            self.label.setText(html)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.ctl.theme
        p.setBrush(QColor(t["card"]))
        p.setPen(QColor(t["accent"]))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 15, 15)

    def enterEvent(self, e):
        self.ctl.hover(True)

    def leaveEvent(self, e):
        self.ctl.hover(False)

    def mousePressEvent(self, e):
        self.ctl.toggle_pin()


# ======================================================= settings editors
class TimeCell(QTimeEdit):
    def __init__(self, minutes=480):
        super().__init__(QTime(minutes // 60, minutes % 60))
        self.setDisplayFormat("h:mm AP")

    def minutes(self):
        t = self.time()
        return t.hour() * 60 + t.minute()


KINDS = ["class", "break", "lunch", "advisory", "other"]


class PeriodsEditor(QWidget):
    HEAD = ["Name", "Start", "End", "Kind", "Class slot"]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(self.HEAD)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        row = QHBoxLayout()
        add = QPushButton("Add period")
        add.clicked.connect(lambda: self.add_row({"name": "New period", "start": 480, "end": 530, "kind": "class", "slot": 0}))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.table.removeRow(i) for i in sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addWidget(self.table)
        lay.addLayout(row)

    def add_row(self, p):
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(p["name"])
        it.setData(Qt.UserRole, p.get("part"))
        self.table.setItem(r, 0, it)
        self.table.setCellWidget(r, 1, TimeCell(p["start"]))
        self.table.setCellWidget(r, 2, TimeCell(p["end"]))
        kc = QComboBox()
        kc.addItems(KINDS)
        kc.setCurrentText(p["kind"] if p["kind"] in KINDS else "other")
        self.table.setCellWidget(r, 3, kc)
        sp = QSpinBox()
        sp.setRange(0, 20)
        sp.setValue(p.get("slot") or 0)
        sp.setSpecialValueText("–")
        self.table.setCellWidget(r, 4, sp)

    def set(self, periods):
        self.table.setRowCount(0)
        for p in sorted(periods, key=lambda x: x["start"]):
            self.add_row(p)

    def get(self):
        out = []
        for r in range(self.table.rowCount()):
            q = {"name": self.table.item(r, 0).text(),
                        "start": self.table.cellWidget(r, 1).minutes(),
                        "end": self.table.cellWidget(r, 2).minutes(),
                        "kind": self.table.cellWidget(r, 3).currentText(),
                        "slot": self.table.cellWidget(r, 4).value() or None}
            part = self.table.item(r, 0).data(Qt.UserRole)
            if part:
                q["part"] = part
            out.append(q)
        return out


class DaysOffEditor(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "From", "To"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setMinimumHeight(140)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(lambda: self.add_row({"name": "Holiday", "start": core.iso(date.today()), "end": core.iso(date.today())}))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.table.removeRow(i) for i in sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addWidget(self.table)
        lay.addLayout(row)

    @staticmethod
    def _de(s):
        d = core.parse_iso(s) or date.today()
        w = QDateEdit(QDate(d.year, d.month, d.day), calendarPopup=True)
        return w

    def add_row(self, r_):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(r_.get("name", "")))
        self.table.setCellWidget(r, 1, self._de(r_["start"]))
        self.table.setCellWidget(r, 2, self._de(r_.get("end") or r_["start"]))

    def set(self, items):
        self.table.setRowCount(0)
        for i in items:
            self.add_row(i)

    def get(self):
        return [{"name": self.table.item(r, 0).text(),
                 "start": self.table.cellWidget(r, 1).date().toString("yyyy-MM-dd"),
                 "end": self.table.cellWidget(r, 2).date().toString("yyyy-MM-dd")}
                for r in range(self.table.rowCount())]


class DateListEditor(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lst = QListWidget()
        self.lst.setMaximumHeight(100)
        self.de = QDateEdit(QDate.currentDate(), calendarPopup=True)
        add = QPushButton("Add")
        add.clicked.connect(self._add)
        rm = QPushButton("Remove")
        rm.clicked.connect(lambda: [self.lst.takeItem(self.lst.row(i)) for i in self.lst.selectedItems()])
        row = QHBoxLayout()
        for w in (self.de, add, rm):
            row.addWidget(w)
        row.addStretch(1)
        lay.addWidget(self.lst)
        lay.addLayout(row)

    def _add(self):
        s = self.de.date().toString("yyyy-MM-dd")
        if not self.lst.findItems(s, Qt.MatchExactly):
            self.lst.addItem(s)

    def set(self, items):
        self.lst.clear()
        for s in sorted(items):
            self.lst.addItem(s)

    def get(self):
        return sorted(self.lst.item(i).text() for i in range(self.lst.count()))


class ColorButton(QPushButton):
    def __init__(self, color):
        super().__init__()
        self.color = color
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet(f"background:{self.color}; border-radius:6px; min-width:50px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self._paint()


# ============================================================ settings tabs
def _scroll(widget):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(widget)
    return sa


class GeneralTab(QWidget):
    def __init__(self, dlg):
        super().__init__()
        lay = QVBoxLayout(self)
        self.login = QCheckBox("Launch at login")
        self.login.setChecked(autostart.is_enabled())
        lay.addWidget(self.login)
        self.msg = QLabel("", objectName="muted")
        lay.addWidget(self.msg)
        hint = session.autostart_hint(autostart.exe())
        if hint:
            lay.addWidget(QLabel(f"Your desktop ({session.desktop()}) doesn't run login entries on its own.\n{hint}",
                                 objectName="muted"))
        lay.addWidget(QLabel(f"Data file: {dlg.ctl.store.path}", objectName="muted"))
        row = QHBoxLayout()
        ex = QPushButton("Export…")
        ex.clicked.connect(self._export)
        im = QPushButton("Import…")
        im.clicked.connect(self._import)
        hp = QPushButton("Help")
        hp.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HELP_URL)))
        for w in (ex, im, hp):
            row.addWidget(w)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        lay.addWidget(QLabel(f"Open the panel from a key:  {session.keybind_hint()}", objectName="muted"))
        lay.addWidget(QLabel(f"Detected: {session.describe()} · window placement: {placement.backend()}", objectName="muted"))
        self.dlg = dlg

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export", "school-schedule.json", "JSON (*.json)")
        if p:
            self.dlg.collect()
            Path(p).write_text(json.dumps(self.dlg.ctl.data, indent=2))

    def _import(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON (*.json)")
        if not p:
            return
        try:
            raw = json.loads(Path(p).read_text())
            self.dlg.ctl.data.clear()
            self.dlg.ctl.data.update(core._merge(core.default_data(), raw))
            self.dlg.ctl.save()
            self.dlg.load()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import failed", str(e))


class DayMapEditor(QWidget):
    """Per-date rotation-day overrides (e.g. a snow day that shifts the A–D letters)."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Date", "Rotation day"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(130)
        self.opts = [("1", 1)]
        row = QHBoxLayout()
        add = QPushButton("Add override")
        add.clicked.connect(lambda: self.add_row(core.iso(date.today()), 1))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.table.removeRow(i) for i in sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addWidget(self.table)
        lay.addLayout(row)

    def _combo(self, value):
        cb = QComboBox()
        for text, n in self.opts:
            cb.addItem(text, n)
        cb.setCurrentIndex(max(cb.findData(value), 0))
        return cb

    def add_row(self, iso_date, value):
        r = self.table.rowCount()
        self.table.insertRow(r)
        d = core.parse_iso(iso_date) or date.today()
        self.table.setCellWidget(r, 0, QDateEdit(QDate(d.year, d.month, d.day), calendarPopup=True))
        self.table.setCellWidget(r, 1, self._combo(value))

    def set_options(self, opts):
        self.opts = opts
        for r in range(self.table.rowCount()):
            cur = self.table.cellWidget(r, 1).currentData()
            self.table.setCellWidget(r, 1, self._combo(cur))

    def set(self, dmap):
        self.table.setRowCount(0)
        for k, v in sorted(dmap.items()):
            self.add_row(k, v)

    def get(self):
        return {self.table.cellWidget(r, 0).date().toString("yyyy-MM-dd"): self.table.cellWidget(r, 1).currentData()
                for r in range(self.table.rowCount())}


BASE_SCHEDULES = ("regular", "short", "advisory")


class SchoolTab(QWidget):
    def __init__(self):
        super().__init__()
        inner = QWidget(objectName="page")
        lay = QVBoxLayout(inner)
        lay.setSpacing(10)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.days = [QCheckBox(n) for n in core.WEEKDAYS]
        dr = QHBoxLayout()
        for c in self.days:
            dr.addWidget(c)
        self.school_only = QCheckBox("Only count school days when rotating")
        self.rot = QSpinBox()
        self.rot.setRange(1, 10)
        self.labels_edit = QLineEdit(placeholderText="e.g. A,B,C,D (blank = 1,2,3…)")
        self.step = QComboBox()
        self.step.addItems(["Forward  (A → B → C → D)", "Backward  (D → C → B → A)"])
        self.anchor = QDateEdit(QDate.currentDate(), calendarPopup=True)
        self.anchor_day = QSpinBox()
        self.anchor_day.setRange(1, 10)
        self.year_on = QCheckBox("Last day of school")
        self.year = QDateEdit(QDate.currentDate().addMonths(6), calendarPopup=True)
        self.adv_on = QCheckBox("Advisory schedule on")
        self.adv_day = QComboBox()
        self.adv_day.addItems(core.WEEKDAYS[:5])
        yr = QHBoxLayout()
        yr.addWidget(self.year_on)
        yr.addWidget(self.year, 1)
        ar = QHBoxLayout()
        ar.addWidget(self.adv_on)
        ar.addWidget(self.adv_day)
        ar.addStretch(1)
        anc = QHBoxLayout()
        anc.addWidget(self.anchor, 1)
        anc.addWidget(QLabel("is rotation day #"))
        anc.addWidget(self.anchor_day)
        # School picker: choosing a school auto-fills bell times, classes and rotation.
        self.tpl = QComboBox()
        for k, v in core.TEMPLATES.items():
            self.tpl.addItem(v, k)
        self.tpl.addItem("Custom (my own settings)", "custom")
        self._tpl_prev = 0
        self.tpl.activated.connect(self._on_school_picked)  # user picks only, not programmatic changes
        self.name_label = QLabel("School name")
        form.addRow("School", self.tpl)
        form.addRow(self.name_label, self.name)
        form.addRow("School days", dr)
        form.addRow("", self.school_only)
        form.addRow("Rotation length", self.rot)
        form.addRow("Direction", self.step)
        note = QLabel("Letter days rotate automatically every school day (weekdays only, skipping the "
                      "days off below). Nothing to enter.", objectName="muted")
        note.setWordWrap(True)
        form.addRow("", note)
        form.addRow("", yr)
        form.addRow("", ar)
        lay.addLayout(form)

        o = QGroupBox("Day overrides (when the letter day isn't what the pattern predicts)")
        ol = QVBoxLayout(o)
        self.daymap = DayMapEditor()
        ol.addWidget(self.daymap)
        # Letter days rotate automatically, so these inputs are not shown. They stay alive (parented, hidden)
        # because they carry the stored rotation settings through load()/collect() untouched.
        for hidden in (o, self.labels_edit, self.anchor, self.anchor_day):
            hidden.setParent(self)
            hidden.hide()
        self.rot.valueChanged.connect(self._opts_changed)
        self.labels_edit.textChanged.connect(self._opts_changed)

        g = QGroupBox("Bell schedule")
        gl = QVBoxLayout(g)
        top = QHBoxLayout()
        self.which = QComboBox()
        self.which.currentIndexChanged.connect(self._switch)
        new = QPushButton("New…")
        new.clicked.connect(self._new_schedule)
        dele = QPushButton("Delete")
        dele.clicked.connect(self._delete_schedule)
        top.addWidget(QLabel("Editing"))
        top.addWidget(self.which, 1)
        top.addWidget(new)
        top.addWidget(dele)
        gl.addLayout(top)
        self.periods = PeriodsEditor()
        gl.addWidget(self.periods)
        lay.addWidget(g)

        lg = QGroupBox("Lunch waves")
        ll = QFormLayout(lg)
        self.lunch_on = QCheckBox("Enable (replaces the times of one class slot)")
        self.lunch_slot = QSpinBox()
        self.lunch_slot.setRange(1, 20)
        self.waves = QLineEdit(placeholderText="e.g. A 11:00-11:30, B 11:35-12:05")
        self.wave_days = QLineEdit(placeholderText="wave index per rotation day, e.g. 1,2")
        ll.addRow(self.lunch_on)
        ll.addRow("Class slot", self.lunch_slot)
        ll.addRow("Waves", self.waves)
        ll.addRow("Wave per day", self.wave_days)
        lay.addWidget(lg)

        d = QGroupBox("Days off (holidays, breaks)")
        dl = QVBoxLayout(d)
        self.off = DaysOffEditor()
        dl.addWidget(self.off)
        lay.addWidget(d)
        s = QGroupBox("Short days")
        sl = QVBoxLayout(s)
        self.short = DateListEditor()
        sl.addWidget(self.short)
        lay.addWidget(s)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))
        self._sched = {}
        self._cur = "regular"
        self.template_applied = None

    # ---- helpers
    def labels(self):
        return [x.strip() for x in self.labels_edit.text().split(",") if x.strip()]

    def _label(self, n):
        labs = self.labels()
        return labs[n - 1] if 0 < n <= len(labs) else str(n)

    def _opts_changed(self, *_):
        self.daymap.set_options([(f"{self._label(i)}  (#{i})", i) for i in range(1, self.rot.value() + 1)])
        self._refresh_which()

    def _friendly(self, key):
        typ, _, n = key.partition(":")
        if n.isdigit():
            return f"{typ.title()} · Day {self._label(int(n))}"
        return typ.title() + (" · default" if typ == "regular" and any(":" in k for k in self._sched) else "")

    def _refresh_which(self, select=None):
        self.which.blockSignals(True)
        self.which.clear()
        order = lambda k: (BASE_SCHEDULES.index(k.split(":")[0]) if k.split(":")[0] in BASE_SCHEDULES else 9, k)
        for k in sorted(self._sched, key=order):
            self.which.addItem(self._friendly(k), k)
        self.which.setCurrentIndex(max(self.which.findData(select or self._cur), 0))
        self._cur = self.which.currentData() or "regular"
        self.which.blockSignals(False)

    def _switch(self, _i):
        self._sched[self._cur] = self.periods.get()
        self._cur = self.which.currentData()
        self.periods.set(self._sched.get(self._cur, []))

    def _new_schedule(self):
        typ, ok = QInputDialog.getItem(self, "New bell schedule", "Day type", list(BASE_SCHEDULES), 0, False)
        if not ok:
            return
        days = ["All rotation days"] + [f"Day {self._label(i)}" for i in range(1, self.rot.value() + 1)]
        pick, ok = QInputDialog.getItem(self, "New bell schedule", "Applies to", days, 0, False)
        if not ok:
            return
        i = days.index(pick)
        key = typ if i == 0 else f"{typ}:{i}"
        self._sched[self._cur] = self.periods.get()
        self._sched.setdefault(key, [dict(p) for p in self._sched[self._cur]])
        self._refresh_which(key)
        self.periods.set(self._sched[self._cur])

    def _delete_schedule(self):
        if ":" not in self._cur:
            QMessageBox.information(self, "Bell schedule", "The base schedules can't be deleted (clear their periods instead).")
            return
        self._sched.pop(self._cur, None)
        self._cur = "regular"
        self._refresh_which("regular")
        self.periods.set(self._sched.get("regular", []))

    def _on_school_picked(self, index):
        if self.tpl.itemData(index) == "custom":
            self._tpl_prev = index
            self._sync_name_visibility()
            return
        if not self._apply_template():
            self.tpl.setCurrentIndex(self._tpl_prev)  # cancelled: put the dropdown back
        self._sync_name_visibility()

    def _sync_name_visibility(self):
        """Wilton fixes the name; other schools/custom let you type one."""
        show = self.tpl.currentData() != "wilton"
        self.name.setVisible(show)
        self.name_label.setVisible(show)

    def _detect_school(self, sc):
        wilton = (sc["name"] == "Wilton High School" and sc["rotationLength"] == 4
                  and (sc.get("dayLabels") or []) == list("ABCD"))
        return "wilton" if wilton else "custom"

    def _apply_template(self):
        tid = self.tpl.currentData()
        if tid == "custom":
            return True
        if QMessageBox.question(self, "Auto-fill", "This replaces your bell schedules, classes and rotation. Continue?") != QMessageBox.Yes:
            return False
        self._tpl_prev = self.tpl.currentIndex()
        t = core.build_template(tid)
        sc = t["school"]
        self.template_applied = t
        if "name" in sc:
            self.name.setText(sc["name"])
        self.rot.setValue(sc["rotationLength"])
        self.labels_edit.setText(",".join(sc["dayLabels"]))
        self.step.setCurrentIndex(1 if sc["rotationStep"] < 0 else 0)
        if "anchorDate" in sc:
            a = core.parse_iso(sc["anchorDate"])
            self.anchor.setDate(QDate(a.year, a.month, a.day))
            self.anchor_day.setValue(sc["anchorDay"])
        self._opts_changed()
        self.daymap.set(sc["dayMap"])
        self._sched = {k: [dict(p) for p in v] for k, v in sc["schedules"].items()}
        for k in BASE_SCHEDULES:
            self._sched.setdefault(k, [])
        self._cur = "regular"
        self._refresh_which("regular")
        self.periods.set(self._sched["regular"])
        return True

    def load(self, data):
        sc = data["school"]
        self.template_applied = None
        self.tpl.blockSignals(True)
        self.tpl.setCurrentIndex(max(self.tpl.findData(self._detect_school(sc)), 0))
        self.tpl.blockSignals(False)
        self._tpl_prev = self.tpl.currentIndex()
        self._sync_name_visibility()
        self.name.setText(sc["name"])
        for i, c in enumerate(self.days):
            c.setChecked(i in sc["weekdays"])
        self.school_only.setChecked(sc["schoolDaysOnly"])
        self.rot.setValue(sc["rotationLength"])
        self.labels_edit.setText(",".join(sc.get("dayLabels") or []))
        self.step.setCurrentIndex(1 if sc.get("rotationStep", 1) < 0 else 0)
        a = core.parse_iso(sc["anchorDate"]) or date.today()
        self.anchor.setDate(QDate(a.year, a.month, a.day))
        self.anchor_day.setValue(sc["anchorDay"])
        ye = core.parse_iso(sc["yearEnd"])
        self.year_on.setChecked(bool(ye))
        if ye:
            self.year.setDate(QDate(ye.year, ye.month, ye.day))
        self.adv_on.setChecked(sc["advisoryEnabled"])
        self.adv_day.setCurrentIndex(min(sc["advisoryWeekday"], 4))
        self._sched = {k: [dict(p) for p in v] for k, v in sc["schedules"].items()}
        for k in BASE_SCHEDULES:
            self._sched.setdefault(k, [])
        self._cur = "regular"
        self._opts_changed()
        self.daymap.set(sc.get("dayMap") or {})
        self._refresh_which("regular")
        self.periods.set(self._sched[self._cur])
        lu = sc["lunch"]
        self.lunch_on.setChecked(lu["enabled"])
        self.lunch_slot.setValue(lu["classSlot"])
        self.waves.setText(", ".join(f"{w['name']} {core.fmt_min(w['start'])}-{core.fmt_min(w['end'])}" for w in lu["waves"]))
        self.wave_days.setText(",".join(str(i + 1) for i in lu["wavePerDay"]))
        self.off.set(sc["daysOff"])
        self.short.set(sc["shortDays"])

    @staticmethod
    def _parse_time(s):
        s = s.strip().upper()
        for f in ("%I:%M %p", "%I:%M%p", "%H:%M"):
            try:
                t = datetime.strptime(s, f)
                return t.hour * 60 + t.minute
            except ValueError:
                pass
        raise ValueError(f"bad time: {s}")

    def _parse_waves(self):
        out = []
        for part in filter(None, (p.strip() for p in self.waves.text().split(","))):
            try:
                name, rng = part.split(" ", 1)
                a, b = rng.split("-")
                out.append({"name": name, "start": self._parse_time(a), "end": self._parse_time(b)})
            except ValueError:
                continue
        return out

    def collect(self, data):
        self._sched[self._cur] = self.periods.get()
        sc = data["school"]
        sc["name"] = self.name.text().strip() or "My School"
        sc["weekdays"] = [i for i, c in enumerate(self.days) if c.isChecked()]
        sc["schoolDaysOnly"] = self.school_only.isChecked()
        sc["rotationLength"] = self.rot.value()
        sc["dayLabels"] = self.labels()[: self.rot.value()]
        sc["rotationStep"] = -1 if self.step.currentIndex() == 1 else 1
        sc["dayMap"] = self.daymap.get()
        sc["anchorDate"] = self.anchor.date().toString("yyyy-MM-dd")
        sc["anchorDay"] = min(self.anchor_day.value(), self.rot.value())
        sc["yearEnd"] = self.year.date().toString("yyyy-MM-dd") if self.year_on.isChecked() else None
        sc["advisoryEnabled"] = self.adv_on.isChecked()
        sc["advisoryWeekday"] = self.adv_day.currentIndex()
        sc["schedules"] = {k: list(v) for k, v in self._sched.items()}
        waves = self._parse_waves()
        try:
            wpd = [max(0, int(x) - 1) for x in self.wave_days.text().split(",") if x.strip()]
        except ValueError:
            wpd = []
        sc["lunch"] = {"enabled": self.lunch_on.isChecked() and bool(waves), "classSlot": self.lunch_slot.value(),
                       "waves": waves, "wavePerDay": wpd or [0]}
        sc["daysOff"] = self.off.get()
        sc["shortDays"] = self.short.get()
        if self.template_applied:
            data["classes"] = self.template_applied["classes"]
            data["plans"] = self.template_applied["plans"]
            sc["classPeriodCount"] = self.template_applied["school"]["classPeriodCount"]


class ClassesTab(QWidget):
    def __init__(self, school_tab: SchoolTab):
        super().__init__()
        self.school = school_tab
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Classes", objectName="muted"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Color"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setMaximumHeight(200)
        row = QHBoxLayout()
        add = QPushButton("Add class")
        add.clicked.connect(lambda: self.add_row({"key": core.new_id(), "name": "New class",
                                                  "colorHex": core.PALETTE[self.table.rowCount() % len(core.PALETTE)]}))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(self._remove)
        rb = QPushButton("Refresh plan grid")
        rb.clicked.connect(self.rebuild_grid)
        for w in (add, rm, rb):
            row.addWidget(w)
        row.addStretch(1)
        lay.addWidget(self.table)
        lay.addLayout(row)
        lay.addWidget(QLabel("Plan: which class meets in each slot on each rotation day", objectName="muted"))
        self.slot_count = QSpinBox()
        self.slot_count.setRange(1, 20)
        sr = QHBoxLayout()
        sr.addWidget(QLabel("Class slots per day"))
        sr.addWidget(self.slot_count)
        sr.addStretch(1)
        self.slot_count.valueChanged.connect(lambda _: self.rebuild_grid())
        lay.addLayout(sr)
        self.grid = QTableWidget(0, 0)
        lay.addWidget(self.grid, 1)
        self.keys = []

    def add_row(self, c):
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(c["name"])
        it.setData(Qt.UserRole, c["key"])
        self.table.setItem(r, 0, it)
        self.table.setCellWidget(r, 1, ColorButton(c["colorHex"]))

    def _remove(self):
        for i in sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(i)
        self.rebuild_grid()

    def classes(self):
        return [{"key": self.table.item(r, 0).data(Qt.UserRole), "name": self.table.item(r, 0).text(),
                 "colorHex": self.table.cellWidget(r, 1).color} for r in range(self.table.rowCount())]

    def current_plans(self):
        out = []
        for r in range(self.grid.rowCount()):
            slots = [self.grid.cellWidget(r, c).currentData() for c in range(self.grid.columnCount())]
            while slots and slots[-1] is None:
                slots.pop()  # trailing unused slots add nothing
            out.append({"day": r + 1, "slots": slots})
        return out

    def rebuild_grid(self, plans=None):
        if plans is None or isinstance(plans, bool):
            plans = self.current_plans()
        rot, n = self.school.rot.value(), self.slot_count.value()
        cls = self.classes()
        self.grid.setRowCount(rot)
        self.grid.setColumnCount(n)
        self.grid.setHorizontalHeaderLabels([f"Slot {i}" for i in range(1, n + 1)])
        self.grid.setVerticalHeaderLabels([f"Day {self.school._label(i)}" for i in range(1, rot + 1)])
        for r in range(rot):
            has_plan = any(p["day"] == r + 1 for p in plans)
            old = next((p["slots"] for p in plans if p["day"] == r + 1), [])
            for c in range(n):
                cb = QComboBox()
                cb.addItem("—", None)
                for k in cls:
                    cb.addItem(k["name"], k["key"])
                if c < len(old):
                    want = old[c]
                elif has_plan:
                    want = None  # slot unused on this day
                else:
                    want = cls[c]["key"] if c < len(cls) else None
                cb.setCurrentIndex(max(cb.findData(want), 0))
                self.grid.setCellWidget(r, c, cb)
        self.grid.resizeColumnsToContents()

    def load(self, data):
        self.table.setRowCount(0)
        for c in data["classes"]:
            self.add_row(c)
        self.slot_count.blockSignals(True)
        self.slot_count.setValue(data["school"]["classPeriodCount"])
        self.slot_count.blockSignals(False)
        self.rebuild_grid(data["plans"])

    def collect(self, data):
        data["classes"] = self.classes()
        data["plans"] = self.current_plans()
        data["school"]["classPeriodCount"] = self.slot_count.value()


class EventsTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Weekly after-school events (practice, clubs, tutoring…)", objectName="muted"))
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Title"] + core.WEEKDAYS[:5] + ["Start", "End", "Location"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        row = QHBoxLayout()
        add = QPushButton("Add event")
        add.clicked.connect(lambda: self.add_row({"title": "New event", "weekdays": [], "start": 900, "end": 960, "location": ""}))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.table.removeRow(i) for i in sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addWidget(self.table)
        lay.addLayout(row)

    def add_row(self, e):
        r = self.table.rowCount()
        self.table.insertRow(r)
        t = QTableWidgetItem(e["title"])
        t.setData(Qt.UserRole, e.get("id") or core.new_id())
        self.table.setItem(r, 0, t)
        for i in range(5):
            c = QTableWidgetItem()
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            c.setCheckState(Qt.Checked if i in e["weekdays"] else Qt.Unchecked)
            self.table.setItem(r, 1 + i, c)
        self.table.setCellWidget(r, 6, TimeCell(e["start"]))
        self.table.setCellWidget(r, 7, TimeCell(e["end"]))
        self.table.setItem(r, 8, QTableWidgetItem(e.get("location", "")))

    def load(self, data):
        self.table.setRowCount(0)
        for e in data["events"]:
            self.add_row(e)

    def collect(self, data):
        data["events"] = [{
            "id": self.table.item(r, 0).data(Qt.UserRole), "title": self.table.item(r, 0).text(),
            "weekdays": [i for i in range(5) if self.table.item(r, 1 + i).checkState() == Qt.Checked],
            "start": self.table.cellWidget(r, 6).minutes(), "end": self.table.cellWidget(r, 7).minutes(),
            "location": self.table.item(r, 8).text()} for r in range(self.table.rowCount())]


class RemindersTab(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.on = QCheckBox("Enable reminders")
        self.cls = QCheckBox("Notify before each class starts")
        self.lead = QSpinBox()
        self.lead.setRange(0, 30)
        self.lead.setSuffix(" min before")
        self.m_on = QCheckBox("Morning summary at")
        self.m_h = QSpinBox()
        self.m_h.setRange(0, 23)
        self.m_h.setSuffix(":00")
        self.e_on = QCheckBox("Evening homework reminder at")
        self.e_h = QSpinBox()
        self.e_h.setRange(0, 23)
        self.e_h.setSuffix(":00")
        self.e_before = QCheckBox("Only mention homework due the next school day")
        f.addRow(self.on)
        f.addRow(self.cls, self.lead)
        f.addRow(self.m_on, self.m_h)
        f.addRow(self.e_on, self.e_h)
        f.addRow(self.e_before)
        t = QPushButton("Send test notification")
        t.clicked.connect(lambda: __import__("school_schedule.notify", fromlist=["x"]).send("School Schedule", "Notifications are working."))
        f.addRow(t)

    def load(self, data):
        r = data["reminders"]
        self.on.setChecked(r["enabled"])
        self.cls.setChecked(r["classStart"])
        self.lead.setValue(r["leadMinutes"])
        self.m_on.setChecked(r["morningOn"])
        self.m_h.setValue(r["morningHour"])
        self.e_on.setChecked(r["eveningOn"])
        self.e_h.setValue(r["eveningHour"])
        self.e_before.setChecked(r["eveningBefore"])

    def collect(self, data):
        r = data["reminders"]
        r.update(enabled=self.on.isChecked(), classStart=self.cls.isChecked(), leadMinutes=self.lead.value(),
                 morningOn=self.m_on.isChecked(), morningHour=self.m_h.value(), eveningOn=self.e_on.isChecked(),
                 eveningHour=self.e_h.value(), eveningBefore=self.e_before.isChecked())


class AppearanceTab(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.theme = QComboBox()
        self.theme.addItems(["system"] + list(THEMES))
        self.accent_on = QCheckBox("Custom accent color")
        self.accent = ColorButton("#0A84FF")
        self.count = QCheckBox("Show countdown (minutes left) on the tray icon")
        self.pill = QCheckBox("Show hover widget (hover it to open the panel)")
        self.corner = QComboBox()
        self.corner.addItems(["top-right", "top-center", "top-left", "bottom-right", "bottom-left"])
        f.addRow("Theme", self.theme)
        r = QHBoxLayout()
        r.addWidget(self.accent_on)
        r.addWidget(self.accent)
        r.addStretch(1)
        f.addRow(r)
        f.addRow(self.count)
        f.addRow(self.pill)
        f.addRow("Widget position", self.corner)
        if not placement.supported():
            note = QLabel("This compositor doesn't let apps position windows, so the hover widget is "
                          "disabled. Use the tray icon or a key bound to `school-schedule --toggle` "
                          "(or run with --x11 to use XWayland).", objectName="muted")
            note.setWordWrap(True)
            f.addRow(note)
            self.pill.setEnabled(False)
            self.corner.setEnabled(False)
        f.addRow(QLabel("Theme “system” follows ~/.config/kdeglobals (e.g. Noctalia) live.", objectName="muted"))

    def load(self, data):
        a = data["appearance"]
        self.pill.setChecked(a["pill"])
        self.corner.setCurrentText(a["pillCorner"])
        self.theme.setCurrentText(a["themeID"])
        self.accent_on.setChecked(bool(a["customAccent"]))
        if a["customAccent"]:
            self.accent.color = a["customAccent"]
            self.accent._paint()
        self.count.setChecked(a["showCountdownInMenuBar"])

    def collect(self, data):
        data["appearance"] = {"themeID": self.theme.currentText(),
                              "customAccent": self.accent.color if self.accent_on.isChecked() else None,
                              "showCountdownInMenuBar": self.count.isChecked(),
                              "pill": self.pill.isChecked(), "pillCorner": self.corner.currentText()}


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle("School Schedule Settings")
        self.resize(940, 700)
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.general = GeneralTab(self)
        self.school = SchoolTab()
        self.classes = ClassesTab(self.school)
        self.events = EventsTab()
        self.reminders = RemindersTab()
        self.appearance = AppearanceTab()
        pages = [("General", self.general), ("School", self.school), ("Classes", self.classes),
                 ("Events", self.events), ("Reminders", self.reminders), ("Appearance", self.appearance)]

        side = QVBoxLayout()
        side.addWidget(QLabel("Settings", objectName="pagetitle"))
        self.nav = QListWidget(objectName="nav")
        self.nav.setFixedWidth(176)
        for n, _ in pages:
            self.nav.addItem(n)
        side.addWidget(self.nav, 1)
        root.addLayout(side)

        right = QVBoxLayout()
        self.header = QLabel("", objectName="pagetitle")
        right.addWidget(self.header)
        self.stack = QStackedWidget()
        for _, w in pages:
            self.stack.addWidget(w)
        right.addWidget(self.stack, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setObjectName("accent")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 1)

        self._names = [n for n, _ in pages]
        self.nav.currentRowChanged.connect(self._page)
        self.nav.setCurrentRow(0)
        self.load()

    def _page(self, i):
        self.stack.setCurrentIndex(i)
        self.header.setText(self._names[i])
        if self.stack.widget(i) is self.classes:
            self.classes.rebuild_grid()

    def load(self):
        d = self.ctl.data
        self.school.load(d)
        self.classes.load(d)
        self.events.load(d)
        self.reminders.load(d)
        self.appearance.load(d)

    def collect(self):
        d = self.ctl.data
        self.school.collect(d)
        if self.school.template_applied:
            self.classes.load(d)  # show the template's classes/plans, then collect them back
        self.classes.collect(d)
        self.events.collect(d)
        self.reminders.collect(d)
        self.appearance.collect(d)
        d["setupDone"] = True

    def accept(self):
        self.collect()
        try:
            autostart.set_enabled(self.general.login.isChecked())
        except OSError as e:
            QMessageBox.warning(self, "Launch at login", str(e))
        self.ctl.save()
        self.saved.emit()
        super().accept()
