"""Detect the desktop/session so the app can adapt (placement, autostart, hints)."""
from __future__ import annotations

import os
import shutil

# Window managers / compositors that do NOT run XDG autostart entries on their own.
MANUAL_AUTOSTART = {"hyprland", "sway", "niri", "i3", "bspwm", "river", "labwc", "wayfire", "openbox", "dwm", "qtile"}


def session_type() -> str:
    t = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if t in ("wayland", "x11"):
        return t
    return "wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11" if os.environ.get("DISPLAY") else ""


def desktop() -> str:
    """Short lowercase name: hyprland, sway, niri, kde, gnome, xfce, cinnamon, ... or 'other'."""
    env = os.environ
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if env.get("SWAYSOCK"):
        return "sway"
    if env.get("NIRI_SOCKET"):
        return "niri"
    names = ":".join(env.get(k, "") for k in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")).lower()
    table = (("kde", "kde"), ("plasma", "kde"), ("gnome", "gnome"), ("unity", "gnome"), ("ubuntu", "gnome"),
             ("cosmic", "cosmic"), ("xfce", "xfce"), ("cinnamon", "cinnamon"), ("x-cinnamon", "cinnamon"),
             ("mate", "mate"), ("lxqt", "lxqt"), ("budgie", "budgie"), ("pantheon", "pantheon"),
             ("deepin", "deepin"), ("river", "river"), ("labwc", "labwc"), ("wayfire", "wayfire"),
             ("i3", "i3"), ("bspwm", "bspwm"), ("openbox", "openbox"), ("qtile", "qtile"), ("dwm", "dwm"))
    for needle, name in table:
        if needle in names:
            return name
    return "other"


def autostart_hint(exe: str = "school-schedule") -> str:
    d = desktop()
    return {
        "hyprland": f"Add to hyprland.conf:  exec-once = {exe}",
        "sway": f"Add to your sway config:  exec {exe}",
        "niri": f'Add to niri config.kdl:  spawn-at-startup "{exe}"',
        "i3": f"Add to your i3 config:  exec --no-startup-id {exe}",
        "bspwm": f"Add to bspwmrc:  {exe} &",
        "river": f"Add to your river init:  riverctl spawn {exe}",
        "labwc": f"Add to labwc autostart:  {exe} &",
        "wayfire": f"Add to wayfire.ini [autostart]:  school = {exe}",
        "openbox": f"Add to openbox autostart:  {exe} &",
        "qtile": f"Start it from your qtile autostart hook:  {exe}",
    }.get(d, "")


def keybind_hint(exe: str = "school-schedule") -> str:
    d = desktop()
    return {
        "hyprland": f"hyprland.conf:  bind = SUPER, S, exec, {exe} --toggle",
        "sway": f"sway config:  bindsym $mod+s exec {exe} --toggle",
        "niri": f'niri config.kdl, in binds:  Mod+S {{ spawn "{exe}" "--toggle"; }}',
        "i3": f"i3 config:  bindsym $mod+s exec {exe} --toggle",
        "kde": f"System Settings → Shortcuts → Add Command → `{exe} --toggle`",
        "gnome": f"Settings → Keyboard → Custom Shortcuts → `{exe} --toggle`",
        "xfce": f"Settings → Keyboard → Application Shortcuts → `{exe} --toggle`",
        "cinnamon": f"Keyboard → Shortcuts → Custom → `{exe} --toggle`",
    }.get(d, f"bind a key to:  {exe} --toggle")


def describe() -> str:
    return f"{desktop()} / {session_type() or 'unknown session'}"


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None
