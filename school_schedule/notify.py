"""Desktop notifications via notify-send (falls back to the tray icon)."""
import shutil
import subprocess


def send(title: str, body: str, tray=None) -> None:
    exe = shutil.which("notify-send")
    if exe:
        try:
            subprocess.Popen([exe, "-a", "School Schedule", "-i", "appointment-soon", title, body])
            return
        except OSError:
            pass
    if tray is not None:
        tray.showMessage(title, body)
