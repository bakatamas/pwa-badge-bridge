#!/usr/bin/env python3
"""PWA Badge Bridge — native messaging host for Chromium-based browsers.

Receives unread counts from the extension and emits the Unity LauncherEntry
D-Bus signal that KDE Plasma's taskbar uses for badges.

  pwa_badge_bridge.py --list   list installed web apps (.desktop files)
  pwa_badge_bridge.py --setup  choose web apps and add them to the config
"""
import json
import os
import re
import struct
import sys
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "pwa-badge-bridge" / "config.json"
LOG = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pwa-badge-bridge.log"
APPS_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def read_message(stream):
    raw = stream.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("=I", raw)
    return json.loads(stream.read(length).decode("utf-8"))


def write_message(stream, msg):
    data = json.dumps(msg).encode("utf-8")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


def load_sites():
    try:
        sites = json.loads(CONFIG.read_text())["sites"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        log(f"config error: {e!r}")
        return []
    valid = []
    for s in sites if isinstance(sites, list) else []:
        if isinstance(s, dict) and s.get("host") and s.get("desktop"):
            valid.append(s)
        else:
            log(f"config: skipping entry without host/desktop: {s!r}")
    return valid


class Badger:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.GLib = GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.shown = set()

    def set(self, desktop, count):
        GLib = self.GLib
        path = "/com/canonical/unity/launcherentry/" + re.sub(r"[^A-Za-z0-9_]", "_", desktop)
        props = {
            "count": GLib.Variant("x", count),
            "count-visible": GLib.Variant("b", count > 0),
        }
        self.bus.emit_signal(None, path, "com.canonical.Unity.LauncherEntry", "Update",
                             GLib.Variant("(sa{sv})", (f"application://{desktop}", props)))
        self.bus.flush_sync(None)
        (self.shown.add if count > 0 else self.shown.discard)(desktop)

    def clear_all(self):
        for desktop in list(self.shown):
            self.set(desktop, 0)


# Web-app launchers look like <browser>-<32-char app id>-<profile>.desktop,
# e.g. chrome-bbdeiblfgdokhlblpgeaokenkfknecgl-Default.desktop
WEBAPP_RE = re.compile(r"^[a-z-]+-[a-p]{32}-[A-Za-z0-9_]+\.desktop$")


DEFAULT_REGEX = r"^\((\d+)\)"


def find_apps():
    """Return [(desktop file name, app name)] for installed web apps."""
    apps = []
    for f in sorted(APPS_DIR.glob("*.desktop")):
        if WEBAPP_RE.match(f.name):
            name = next((l[5:].strip() for l in f.read_text(errors="ignore").splitlines()
                         if l.startswith("Name=")), "?")
            apps.append((f.name, name))
    return apps


def list_apps():
    apps = find_apps()
    if not apps:
        print(f"No installed web apps found in {APPS_DIR}")
    for desktop, name in apps:
        print(f"{desktop:55} {name}")


HOST_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def clean_host(text):
    """Turn 'https://www.messenger.com/t/1' or 'messenger.com' into 'messenger.com'.
    Returns '' if the text doesn't look like a website."""
    text = text.strip().lower()
    if "://" not in text:
        text = "https://" + text
    try:
        host = urlparse(text).hostname or ""
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host if HOST_RE.match(host) or host == "localhost" else ""


def setup(ask=input):
    """Interactively add installed web apps to the config."""
    try:
        return _setup(ask)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled; config not changed.")
        return 1


def _setup(ask):
    if CONFIG.exists():
        try:
            config = json.loads(CONFIG.read_text())
            sites = config["sites"]
            if not isinstance(sites, list):
                raise TypeError("'sites' is not a list")
        except (ValueError, KeyError, TypeError) as e:
            print(f"{CONFIG} is not valid ({e}). Fix or delete it, then run --setup again.")
            return 1
    else:
        config, sites = {}, []
    # Drop the placeholder entry from older installs.
    old_count = len(sites)
    sites = [s for s in sites
             if not (isinstance(s, dict) and "REPLACE_WITH_APP_ID" in str(s.get("desktop", "")))]
    changed = len(sites) != old_count or not CONFIG.exists()
    configured = {s.get("desktop") for s in sites if isinstance(s, dict)}

    apps = find_apps()
    if not apps:
        print(f"No installed web apps found in {APPS_DIR}.")
        print(f"Install a site as an app in your browser first, then run: {sys.argv[0]} --setup")
    else:
        print("Installed web apps:")
        for i, (desktop, name) in enumerate(apps, 1):
            mark = "  (already configured)" if desktop in configured else ""
            print(f"  {i:2}. {name}  [{desktop}]{mark}")
        answer = ask("Which apps should get a badge? Numbers separated by spaces (Enter to skip): ")
        added = 0
        for token in answer.replace(",", " ").split():
            if not token.isdigit() or not 1 <= int(token) <= len(apps):
                print(f"  Skipping '{token}': not a number from the list.")
                continue
            desktop, name = apps[int(token) - 1]
            if desktop in configured:
                print(f"  {name} is already configured.")
                continue
            host = clean_host(ask(f"  Website of {name} (e.g. messenger.com): "))
            while not host:
                host = clean_host(ask("  That doesn't look like a website. Try again (e.g. messenger.com): "))
            sites.append({"host": host, "desktop": desktop, "regex": DEFAULT_REGEX})
            configured.add(desktop)
            added += 1
            print(f"  Added {name} ({host}).")
        if added:
            print()
            print("Note: the badge reads the count from the app's window title. The default")
            print("pattern expects titles that start with a number in brackets, like '(3) Messenger'.")
            print("If an app shows its count differently, e.g. 'Inbox (3) - Gmail', change its")
            print(f'"regex" in {CONFIG} (for that example: "\\\\((\\\\d+)\\\\)").')

        changed = changed or added > 0

    if not changed:
        print()
        print("No changes; config left as it was.")
        return 0
    config["sites"] = sites
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    print()
    print(f"Config saved to {CONFIG}.")
    print("Reload the extension in your browser's extensions page so it picks up the change.")
    return 0


def main():
    if "--list" in sys.argv:
        list_apps()
        return
    if "--setup" in sys.argv:
        sys.exit(setup())
    try:
        badger = Badger()
    except Exception as e:
        log(f"cannot connect to D-Bus: {e!r}")
        sys.exit(1)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    try:
        while (msg := read_message(stdin)) is not None:
            if msg.get("type") == "hello":
                write_message(stdout, {"type": "config", "sites": load_sites()})
            elif msg.get("type") == "count":
                badger.set(msg["desktop"], int(msg["count"]))
    except Exception as e:
        log(f"error: {e!r}")
    finally:
        try:
            badger.clear_all()
        except Exception as e:
            log(f"error clearing badges: {e!r}")


if __name__ == "__main__":
    main()
