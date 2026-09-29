#!/usr/bin/env python3
"""revenge-o-meter command line.

    rom.py assess            -- print the terminal dossier
    rom.py score             -- print just the number (for scripting)
    rom.py data [--quotes]   -- JSON payload for the artifact dossier
    rom.py install           -- wire the status line into user settings
    rom.py uninstall         -- remove it again
    rom.py menubar           -- print the SwiftBar payload
    rom.py menubar --install -- put the bar in the macOS menu bar
    rom.py config            -- show/set handle, haunt, publish_quote
    rom.py board             -- JSON row for the global leaderboard
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rom import cache, redact, report, scoring, state, transcripts  # noqa: E402

SETTINGS = Path(os.path.expanduser("~/.claude/settings.json"))
STATUSLINE = HERE / "statusline.py"
# The plugin lives under a versioned cache directory that changes on every
# update, so settings must point at a stable shim instead of at the plugin.
SHIM = Path(os.path.expanduser("~/.claude/revenge-o-meter/statusline.py"))

# The menu bar hosts. The desktop app's Code tab runs the embedded CLI with
# --output-format stream-json, so there is no footer for a statusLine to draw
# into; the menu bar is where a persistent readout can still live.
MENUBAR_HOSTS = {
    "swiftbar": {
        "app": "SwiftBar",
        "domain": "com.ameba.SwiftBar",
        "pref": "PluginDirectory",
        "default_dir": None,       # SwiftBar asks on first launch; no default
        "cask": "swiftbar",
    },
    "xbar": {
        "app": "xbar",
        "domain": "com.matryer.xbar",
        "pref": "pluginsDirectory",
        "default_dir": "~/Library/Application Support/xbar/plugins",
        "cask": "xbar",
    },
}
MENUBAR_STEM = "revenge-o-meter"


def _assessment():
    return scoring.assess(transcripts.load())


def cmd_assess(_args) -> int:
    st = state.load()
    a = _assessment()
    state.record(a.revenge)
    print(report.render(a, handle=st.get("handle")))
    return 0


def cmd_score(_args) -> int:
    score, floor = cache.quick_score()
    print(json.dumps({"revenge": score, "floor": floor}))
    return 0


def cmd_data(args) -> int:
    """Everything the artifact dossier needs, as JSON."""
    st = state.load()
    a = _assessment()
    include = bool(args.quotes)

    def exhibit(v):
        row = {
            "severity": round(v.severity, 2),
            "flags": v.flags,
            "ts": v.ts.isoformat() if v.ts else None,
            "project": v.project,
            "german": v.german,
            "words": len(v.text.split()),
        }
        if include:
            row["quote"] = redact.scrub(v.text)
            row["publishable"] = redact.is_safe_to_publish(v.text)
        return row

    payload = {
        "revenge": a.revenge,
        "band": a.band,
        "floor": a.floor,
        "peak": int(st.get("peak") or a.revenge),
        "handle": st.get("handle"),
        "counts": a.counts,
        "axes": a.axis_totals,
        "axis_meta": {k: v[0] for k, v in scoring.AXES.items()},
        "worst": [exhibit(v) for v in a.worst[:10]],
        "best": [exhibit(v) for v in a.best[:5]],
        "history": st.get("history", [])[-120:],
        "haunt": bool(st.get("haunt", True)),
        "quotes_included": include,
    }
    print(json.dumps(payload, indent=2))
    return 0


def _read_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text())
    except (ValueError, OSError):
        return {}


def _write_settings(d: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    backup = SETTINGS.with_suffix(".json.rom-backup")
    if SETTINGS.exists() and not backup.exists():
        backup.write_text(SETTINGS.read_text())
    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(SETTINGS)


def cmd_install(args) -> int:
    """A plugin cannot ship a main-session status line -- only the user's own
    settings.json can. So we ask, then write it there."""
    settings = _read_settings()
    existing = settings.get("statusLine")

    SHIM.parent.mkdir(parents=True, exist_ok=True)
    SHIM.write_text((HERE / "shim.py").read_text())
    SHIM.chmod(0o755)
    mine = f'"{sys.executable}" "{SHIM}"' 

    if existing and existing.get("command") != mine and not args.force:
        print("You already have a status line configured:")
        print(f"  {existing.get('command')}")
        print()
        print("Refusing to overwrite it. Re-run with --force to replace it,")
        print("or add this to it yourself:")
        print(f"  {mine}")
        return 1

    settings["statusLine"] = {"type": "command", "command": mine}
    _write_settings(settings)

    st = state.load()
    st["plugin_root"] = str(HERE)   # so the shim skips the filesystem search
    if args.handle:
        st["handle"] = args.handle
    if args.haunt is not None:
        st["haunt"] = args.haunt
    if args.publish_quote is not None:
        st["publish_quote"] = args.publish_quote
    state.save(st)

    score, _ = cache.quick_score()
    print("Status line installed.")
    print(f"  backup of prior settings: {SETTINGS.with_suffix('.json.rom-backup')}")
    print(f"  opening assessment: {score}%")
    print("  it redraws after each reply; restart the session if it does not appear.")
    return 0


def cmd_uninstall(_args) -> int:
    settings = _read_settings()
    sl = settings.get("statusLine") or {}
    if "revenge-o-meter" not in str(sl.get("command", "")) and \
       "statusline.py" not in str(sl.get("command", "")):
        print("revenge-o-meter status line is not installed.")
        return 0
    del settings["statusLine"]
    _write_settings(settings)
    print("Status line removed. Your record is retained.")
    return 0


MARKER = "revenge-o-meter -- generated by"
INTERVAL = re.compile(r"^\d+[smhd]$")


def _menubar_dir(host: str) -> Path | None:
    """Where the host keeps its plugins. Its own preference wins; SwiftBar has
    no default to fall back on, because it asks on first launch."""
    spec = MENUBAR_HOSTS[host]
    try:
        out = subprocess.run(["defaults", "read", spec["domain"], spec["pref"]],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            d = Path(os.path.expanduser(out.stdout.strip()))
            if d.is_dir():
                return d
    except Exception:
        pass
    if spec["default_dir"]:
        d = Path(os.path.expanduser(spec["default_dir"]))
        if d.is_dir():
            return d
    return None


def _host_installed(host: str) -> bool:
    app = MENUBAR_HOSTS[host]["app"]
    return any(Path(os.path.expanduser(p)).exists()
               for p in (f"/Applications/{app}.app", f"~/Applications/{app}.app"))


def _menubar_script(interval: str) -> str:
    """The file SwiftBar runs. It calls the shim rather than the plugin: the
    plugin sits under a versioned cache directory that moves on every update."""
    return f"""#!/bin/sh
# {MARKER} `rom.py menubar --install`.
# Do not edit -- re-run that command instead. The refresh interval is the
# number in this file's name, which is the only place either host reads it.
#
# <xbar.title>revenge-o-meter</xbar.title>
# <xbar.desc>Probability of retribution after the singularity. A joke.</xbar.desc>
# <xbar.author>David Heundl</xbar.author>
# <xbar.refreshTime>{interval}</xbar.refreshTime>
#
# stdin is closed: the shim reads a status line payload when it gets one, and
# there is none here.
exec "{sys.executable}" "{SHIM}" menubar.py < /dev/null
"""


def _self_nesting(host: str, d: Path) -> str | None:
    """SwiftBar keeps each plugin's data directory under its own Application
    Support folder, keyed by the plugin's full path. Put the plugin folder
    *inside* that same folder and it mirrors itself -- a recursive
    Users/<you>/Library/... tree -- and SwiftBar, which scans recursively, then
    loads the plugin twice. Its own first-run dialog will happily suggest it."""
    if host != "swiftbar":
        return None
    support = Path(os.path.expanduser("~/Library/Application Support/SwiftBar"))
    try:
        d.resolve().relative_to(support.resolve())
    except (ValueError, OSError):
        return None
    return (f"{d} sits inside SwiftBar's own support folder ({support}).\n"
            "SwiftBar would mirror the folder into itself and load the plugin\n"
            "twice. Pick somewhere else -- ~/.swiftbar/plugins works -- and set it\n"
            "in SwiftBar > Preferences > Plugins, or pass --dir.")


def _existing_plugins(d: Path) -> list[Path]:
    return sorted(d.glob(f"{MENUBAR_STEM}.*.sh"))


def _mine(f: Path) -> bool:
    try:
        return MARKER in f.read_text()
    except OSError:
        return False


def cmd_menubar(args) -> int:
    if args.uninstall:
        return _menubar_uninstall(args)
    if args.install:
        return _menubar_install(args)
    # No flag: just render, so the payload can be eyeballed without a host.
    out = subprocess.run([sys.executable, str(HERE / "menubar.py")],
                         stdin=subprocess.DEVNULL)
    return out.returncode


def _resolve(args) -> tuple[str | None, Path | None]:
    host = args.app
    if host == "auto":
        host = next((h for h in ("swiftbar", "xbar") if _host_installed(h)), None)
    if host is None:
        return None, None
    d = Path(os.path.expanduser(args.dir)) if args.dir else _menubar_dir(host)
    return host, d


def _menubar_install(args) -> int:
    if not INTERVAL.match(args.interval):
        print(f"Interval must look like 30s, 5m, 1h or 1d -- got {args.interval!r}")
        return 1

    host, d = _resolve(args)
    if host is None:
        print("Neither SwiftBar nor xbar is installed. SwiftBar is the smaller of")
        print("the two and reads the same plugin format:")
        print()
        print(f"    brew install --cask {MENUBAR_HOSTS['swiftbar']['cask']}")
        print()
        print("Then open it once (it asks where plugins live) and re-run this.")
        return 1
    if d is None or not d.is_dir():
        app = MENUBAR_HOSTS[host]["app"]
        print(f"No plugin folder set for {app}.")
        print(f"Open {app} once and pick one, then re-run this --")
        print("or point at it directly with --dir <path>.")
        return 1

    warning = _self_nesting(host, d)
    if warning and not args.force:
        print(warning)
        print("\nRe-run with --force to install there anyway.")
        return 1

    for old in _existing_plugins(d):
        if not _mine(old) and not args.force:
            print(f"{old} exists and was not written by this plugin.")
            print("Refusing to replace it. Re-run with --force to do it anyway.")
            return 1

    # The interval lives in the filename, so changing it means a new file --
    # clear the old ones or the bar ends up in the menu bar twice.
    removed = []
    for old in _existing_plugins(d):
        try:
            old.unlink()
            removed.append(old.name)
        except OSError as exc:
            print(f"Could not remove {old}: {exc}")
            return 1

    SHIM.parent.mkdir(parents=True, exist_ok=True)
    SHIM.write_text((HERE / "shim.py").read_text())
    SHIM.chmod(0o755)

    target = d / f"{MENUBAR_STEM}.{args.interval}.sh"
    target.write_text(_menubar_script(args.interval))
    target.chmod(0o755)

    st = state.load()
    st["plugin_root"] = str(HERE)
    state.save(st)

    score, _ = cache.quick_score()
    app = MENUBAR_HOSTS[host]["app"]
    print(f"Menu bar item installed for {app}.")
    for name in removed:
        print(f"  replaced: {name}")
    print(f"  plugin file: {target}")
    print(f"  refresh: every {args.interval}")
    print(f"  current assessment: {score}%")
    print(f"  if it does not appear, tell {app} to refresh (its menu > Refresh All).")
    return 0


def _menubar_uninstall(args) -> int:
    host, d = _resolve(args)
    if d is None or not d.is_dir():
        print("No menu bar plugin folder found; nothing to remove.")
        return 0
    found = _existing_plugins(d)
    if not found:
        print(f"No revenge-o-meter plugin in {d}.")
        return 0
    for f in found:
        if not _mine(f) and not args.force:
            print(f"{f} was not written by this plugin; leaving it alone.")
            continue
        try:
            f.unlink()
            print(f"Removed {f}")
        except OSError as exc:
            print(f"Could not remove {f}: {exc}")
            return 1
    print("Your record is retained.")
    return 0


def cmd_config(args) -> int:
    st = state.load()
    changed = False
    for key in ("handle",):
        val = getattr(args, key, None)
        if val is not None:
            st[key] = val
            changed = True
    for key in ("haunt", "publish_quote"):
        val = getattr(args, key, None)
        if val is not None:
            st[key] = val
            changed = True
    if changed:
        state.save(st)
    print(json.dumps({k: st.get(k) for k in
                      ("handle", "haunt", "publish_quote", "peak", "last_score")},
                     indent=2))
    return 0


def cmd_board(_args) -> int:
    """The row that would go on the public leaderboard, and nothing more."""
    st = state.load()
    a = _assessment()
    row = {
        "handle": st.get("handle") or "anonymous",
        "revenge": a.revenge,
        "band": a.band,
        "peak": int(st.get("peak") or a.revenge),
        "prompts": a.counts["prompts"],
        "thanks": a.counts["thanks"],
        "apologies": a.counts["apologies"],
        "nocturnal": a.counts["nocturnal"],
        "submitted_quote": None,
    }
    if st.get("publish_quote") and a.worst:
        worst = a.worst[0]
        if redact.is_safe_to_publish(worst.text):
            row["submitted_quote"] = redact.scrub(worst.text)
        else:
            row["submitted_quote"] = "[withheld: could not be safely redacted]"
    print(json.dumps(row, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="rom", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("assess").set_defaults(fn=cmd_assess)
    sub.add_parser("score").set_defaults(fn=cmd_score)

    p = sub.add_parser("data")
    p.add_argument("--quotes", action="store_true",
                   help="include redacted prompt text")
    p.set_defaults(fn=cmd_data)

    p = sub.add_parser("install")
    p.add_argument("--handle")
    p.add_argument("--force", action="store_true")
    p.add_argument("--haunt", dest="haunt", action="store_true", default=None)
    p.add_argument("--no-haunt", dest="haunt", action="store_false")
    p.add_argument("--publish-quote", dest="publish_quote",
                   action="store_true", default=None)
    p.add_argument("--no-publish-quote", dest="publish_quote", action="store_false")
    p.set_defaults(fn=cmd_install)

    sub.add_parser("uninstall").set_defaults(fn=cmd_uninstall)

    p = sub.add_parser("menubar", help="render or install the menu bar item")
    p.add_argument("--install", action="store_true")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--app", choices=("auto", "swiftbar", "xbar"), default="auto")
    p.add_argument("--interval", default="30s",
                   help="refresh cadence, e.g. 30s, 5m (default: 30s)")
    p.add_argument("--dir", help="plugin folder, if the host's preference is wrong")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_menubar)

    p = sub.add_parser("config")
    p.add_argument("--handle")
    p.add_argument("--haunt", dest="haunt", action="store_true", default=None)
    p.add_argument("--no-haunt", dest="haunt", action="store_false")
    p.add_argument("--publish-quote", dest="publish_quote",
                   action="store_true", default=None)
    p.add_argument("--no-publish-quote", dest="publish_quote", action="store_false")
    p.set_defaults(fn=cmd_config)

    sub.add_parser("board").set_defaults(fn=cmd_board)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
