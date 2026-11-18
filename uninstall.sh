#!/bin/sh
# Remove the launcher, menu entry, icon and autostart entry. Your data in ~/.config/school-schedule is kept.
rm -f "$HOME/.local/bin/school-schedule" "$HOME/.local/share/applications/school-schedule.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/school-schedule.svg" \
      "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/school-schedule.desktop"
echo "Removed. (Settings/data kept in ${XDG_CONFIG_HOME:-$HOME/.config}/school-schedule)"
