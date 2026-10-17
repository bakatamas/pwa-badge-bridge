# PWA Badge Bridge

Shows unread counts from installed web apps (PWAs) as badges on their **KDE Plasma** taskbar icons.

Chrome-based browsers don't show PWA badges on Linux. Messenger, for example, puts the unread count in its window title — `(3) Messenger` — but the taskbar icon stays blank. This project reads that count and puts it on the icon.

It works for any web app that puts a number in its title, and you choose which apps through a small config file.

## How it works

1. A browser extension watches the tab titles of the sites you configured and extracts the number with a regex.
2. It sends the count to a small Python helper (a native messaging host).
3. The helper emits the `com.canonical.Unity.LauncherEntry` D-Bus signal for the app's `.desktop` file, which Plasma shows as a badge.

The extension uses only the `tabs` and `nativeMessaging` permissions. It doesn't inject anything into pages, and nothing leaves your computer.

## Requirements

- KDE Plasma (tested on Plasma 6, Wayland, CachyOS)
- Google Chrome (tested). The installer also registers the helper for Chromium, Brave, Vivaldi and Edge, but those are untested.
- Python 3 with PyGObject (`python-gobject` on Arch, `python3-gi` on Debian/Ubuntu)
- The web app installed as an app from your browser's menu (in Chrome: *Install page as app*)

## Install

```
./install.sh
```

The installer copies the helper to `~/.local/bin/pwa-badge-bridge` and registers it with every supported browser it finds. Then it lists your installed web apps and asks which ones should get a badge:

```
Installed web apps:
   1. Messenger  [chrome-bbdeiblfgdokhlblpgeaokenkfknecgl-Default.desktop]
   2. Gmail  [chrome-fmpnliohjhemenmnlpbfagaolkdacoja-Default.desktop]
Which apps should get a badge? Numbers separated by spaces (Enter to skip): 1
  Website of Messenger (e.g. messenger.com): messenger.com
  Added Messenger (messenger.com).
```

It asks for each app's website because the app's launcher file doesn't record it. You can type the domain or paste any URL from the site. If the URL has a path, it asks whether to count only pages under it; say yes for apps that live in a folder of a larger site, like `https://example.com/tools/kanban/`. The choices are saved to `~/.config/pwa-badge-bridge/config.json`.

Then open your browser's extensions page (`chrome://extensions`), turn on **Developer mode**, click **Load unpacked**, and select the `extension` folder.

To add more apps later, run `~/.local/bin/pwa-badge-bridge --setup` and reload the extension.

> **You may need to change the title pattern.** The badge reads the count from the app's window title. The default pattern expects titles that **start** with a number in brackets, like `(3) Messenger`. If an app shows its count elsewhere, e.g. `Inbox (3) - Gmail`, or not in brackets, edit that app's `regex` in the config (see below). To see an app's exact title, open DevTools in the app window (Ctrl+Shift+I) and run `document.title`.

## Configuration

`~/.config/pwa-badge-bridge/config.json` (written by the setup, editable by hand):

```json
{
  "sites": [
    {
      "host": "messenger.com",
      "desktop": "chrome-bbdeiblfgdokhlblpgeaokenkfknecgl-Default.desktop",
      "regex": "^\\((\\d+)\\)"
    }
  ]
}
```

- **host**: the site's domain. Subdomains match too, so `messenger.com` covers `www.messenger.com`.
- **path** (optional): only count pages under this folder, e.g. `"/tools/kanban"` matches `/tools/kanban/` and `/tools/kanban/board`, but not `/tools/kanban2`. Use it for apps that live in a folder of a larger site. If several entries match a page, the one with the longest path wins.
- **desktop**: the app's `.desktop` file name, from `pwa-badge-bridge --list`.
- **regex** (optional): finds the count in the title. The first capture group must be the number. The default, `^\((\d+)\)`, matches titles that start with `(3)`. For a count elsewhere in the title, drop the `^`, e.g. `\((\d+)\)`.

**After changing the config, reload the extension** on the extensions page. The helper reads the config only when it starts.

If several tabs of the same site are open, the badge shows the highest count. When a title briefly loses its number, for example while Messenger flashes "X messaged you", the badge waits 3 seconds before clearing.

## Troubleshooting

- **Test without waiting for a message.** Open DevTools in the app window (Ctrl+Shift+I) and run `document.title = "(3) Test"`. Messenger may reset the title shortly afterwards; the badge then clears after 3 seconds.
- **Check the helper log:** `~/.cache/pwa-badge-bridge.log` (for example, config syntax errors).
- **Check the extension:** on the extensions page, click *service worker* under PWA Badge Bridge and look for errors.
- **Check that the signal is sent:** run `dbus-monitor "interface='com.canonical.Unity.LauncherEntry'"` while the count changes. If signals appear but no badge, Plasma isn't linking the window to that `.desktop` file. Right-click the window title bar → *More Actions → Configure Special Window Settings → Add Property → Detect Window Properties*, and compare *Desktop file name* with your config.
- **Pinned icon shows no badge:** unpin it, open the app from the app menu, and pin it again from the running window.

## Uninstall

1. Remove the extension from the extensions page.
2. Run:
   ```
   find ~/.config -name hu.celest.pwa_badge_bridge.json -path '*NativeMessagingHosts*' -delete
   rm -rf ~/.local/bin/pwa-badge-bridge ~/.config/pwa-badge-bridge ~/.cache/pwa-badge-bridge.log
   ```

## Known limitations

- If Plasma restarts while the browser is running, the badge stays empty until the count next changes.
- Apps that don't put their unread count in the title can't be supported.
- Only tested with Google Chrome on KDE Plasma 6 (Wayland).

## License

MIT, see [LICENSE](LICENSE).
