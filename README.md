# School Schedule for Linux

A tray/overlay class schedule: what class you're in, a live countdown, today's periods,
homework and after-school events. Re-creation of the macOS menu-bar app *School Schedule 1.0*.

**Hover the small widget (top corner) and the panel opens; move away and it closes.** Click the
widget, the tray icon, or run `school-schedule --toggle` to pin it open.

## Wilton High School is built in
The default schedule is Wilton's A–D block rotation with all bell times (from `schoology-wrapper`).
The letter day **rotates automatically**: one step per school day, Mon–Fri only, skipping any
*Days off* you add (Settings → School). Nothing to type. The pattern follows the known week
(Mon B, Tue A, Wed D, Thu C, Fri B), i.e. backwards; Settings → School → Direction flips it. Pick the school from the **School** dropdown (Wilton High School, generic presets, or Custom).
Add holidays/breaks under *Days off*, or the rotation will advance through them.

## Install (any distro, no root)
    ./install.sh              # private virtualenv + PySide6 from PyPI (needs python3 ≥ 3.9 with venv)
    ./install.sh --system     # use PySide6 from your package manager instead (musl/Alpine, NixOS, …)
    pipx install .            # alternative
    ./uninstall.sh            # removes launcher/menu entry/icon/autostart; keeps your data

    school-schedule [--toggle | --show | --settings | --quit] [--x11]

Optional: `notify-send` (libnotify) for the most reliable notifications; otherwise Qt's tray message is used.

## Desktop support
| Desktop / session | Tray icon | Hover widget + panel placement | Status |
|---|---|---|---|
| **Hyprland** (Wayland) | via bar's tray (Waybar `tray`, Quickshell, …) | `hyprctl` (Lua + classic dispatch) | **tested live** |
| **Sway** (Wayland) | via bar's tray | `swaymsg` | commands unit-tested with mocks, not run on Sway |
| **KDE Plasma** (Wayland/X11) | native | KWin script over D-Bus (X11: Qt) | script syntax-checked, not run on Plasma |
| **X11** (any WM: i3, XFCE, Cinnamon, MATE, LXQt, …) | native/SNI | Qt `move()` | logic tested offscreen, not on real X11 |
| **GNOME** | needs the AppIndicator extension | via XWayland automatically (if `libxcb-cursor` present), else disabled | not tested on GNOME |
| Other Wayland compositors (niri, river, labwc, COSMIC…) | via bar's tray | widget disabled unless `--x11`; use tray or `--toggle` | not tested |

Tray icons use the StatusNotifier protocol, which never reports hovering, so hover is done by
the small floating widget, not the tray icon. Where windows can't be placed, the widget is off
and everything else still works.

### Theme
"System" theme follows `~/.config/kdeglobals` (KDE, Noctalia, …) and re-themes live when it
changes; on GNOME it uses the Qt palette plus the GNOME accent colour; otherwise the Qt palette.

### Autostart & keybinds
Settings → General shows the exact line for your desktop (e.g. Hyprland: `exec-once = school-schedule`;
Sway: `exec school-schedule`; KDE/GNOME/XFCE use the built-in "Launch at login" XDG entry) and a
keybind for `--toggle`.

## Develop
Data model + engine: `school_schedule/core.py` (no Qt). UI: `ui.py`. Tray/hover/reminders:
`main.py`. Placement backends: `placement.py`. Desktop detection: `session.py`.
