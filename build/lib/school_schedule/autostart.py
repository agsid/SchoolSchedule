"""Launch-at-login via an XDG autostart .desktop entry."""
import os
import shutil
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "school-schedule"


def exe() -> str:
    """Prefer an installed `school-schedule` on PATH (pipx/pip/distro), else the checkout launcher."""
    return shutil.which("school-schedule") or str(LAUNCHER)


def _path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "school-schedule.desktop"


def desktop_entry() -> str:
    return (
        "[Desktop Entry]\nType=Application\nName=School Schedule\n"
        "Comment=Menu-bar style class schedule, countdown and homework\n"
        f"Exec={exe()}\nIcon=school-schedule\nCategories=Office;Education;\n"
        "X-GNOME-Autostart-enabled=true\nX-KDE-autostart-after=panel\nStartupNotify=false\nTerminal=false\n"
    )


def is_enabled() -> bool:
    return _path().exists()


def set_enabled(on: bool) -> None:
    p = _path()
    if on:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(desktop_entry())
    elif p.exists():
        p.unlink()
