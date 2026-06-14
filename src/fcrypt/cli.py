"""Command-line interface for fcrypt.

This module exposes ``main()``, which is wired up as the ``fcrypt`` console
script (see pyproject.toml) and is also used by ``python -m fcrypt``.

Launches the TUI by default. Also supports headless CLI usage:

    fcrypt enc <file>          encrypt a file
    fcrypt dec <file.fcr>      decrypt a file
    fcrypt tui [dir]           open the TUI (optionally at a directory)
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from . import __version__, core
from .tui import main as tui_main, human_size


def _cli_encrypt(args) -> int:
    if not os.path.isfile(args.path):
        print(f"error: not a file: {args.path}", file=sys.stderr)
        return 1
    pw = getpass.getpass("Password: ")
    if not pw:
        print("error: empty password", file=sys.stderr)
        return 1
    if getpass.getpass("Confirm:  ") != pw:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    try:
        res = core.encrypt_file(args.path, pw, out_path=args.out,
                                overwrite=args.force)
    except core.FcryptError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"encrypted -> {res.out_path} "
          f"({human_size(res.in_bytes)} -> {human_size(res.out_bytes)})")
    return 0


def _cli_decrypt(args) -> int:
    if not os.path.isfile(args.path):
        print(f"error: not a file: {args.path}", file=sys.stderr)
        return 1
    pw = getpass.getpass("Password: ")
    try:
        res = core.decrypt_file(args.path, pw, out_path=args.out,
                                overwrite=args.force)
    except core.WrongPasswordError:
        print("error: wrong password or corrupted file", file=sys.stderr)
        return 1
    except core.FcryptError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"decrypted -> {res.out_path} (original: {res.original_name})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fcrypt",
        description="Encrypt/decrypt files (text, images, PDF, docs) "
                    "with AES-256-GCM. Run with no command (or 'tui') "
                    "to launch the interactive browser.",
        epilog="Examples:\n"
               "  fcrypt                 open TUI in current directory\n"
               "  fcrypt tui ~/Documents open TUI in a directory\n"
               "  fcrypt enc report.pdf  encrypt a file\n"
               "  fcrypt dec report.pdf.fcr  decrypt a file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-V", "--version", action="version",
                   version=f"fcrypt {__version__}")
    sub = p.add_subparsers(dest="cmd")

    pt = sub.add_parser("tui", help="launch the interactive TUI (default)")
    pt.add_argument("dir", nargs="?", help="directory to open")
    pt.set_defaults(func=None)

    pe = sub.add_parser("enc", help="encrypt a file (headless)")
    pe.add_argument("path")
    pe.add_argument("-o", "--out", help="output path")
    pe.add_argument("-f", "--force", action="store_true", help="overwrite output")
    pe.set_defaults(func=_cli_encrypt)

    pd = sub.add_parser("dec", help="decrypt a file (headless)")
    pd.add_argument("path")
    pd.add_argument("-o", "--out", help="output path")
    pd.add_argument("-f", "--force", action="store_true", help="overwrite output")
    pd.set_defaults(func=_cli_decrypt)

    return p


def _launch_tui(start: str | None) -> int:
    start = start or os.getcwd()
    start = os.path.expanduser(start)
    if not os.path.isdir(start):
        print(f"error: not a directory: {start}", file=sys.stderr)
        return 1
    try:
        tui_main(start)
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = getattr(args, "cmd", None)
    if cmd in ("enc", "dec"):
        return args.func(args)
    if cmd == "tui":
        return _launch_tui(getattr(args, "dir", None))
    # no subcommand -> default TUI in current directory
    return _launch_tui(None)


if __name__ == "__main__":
    sys.exit(main())
