#!/usr/bin/env bash
#
# fcrypt installer for Linux.
#
# Installs `fcrypt` as a system-wide command in an ISOLATED environment so it
# never conflicts with your system Python packages. It prefers pipx (the
# recommended way to install Python CLI apps); if pipx is missing it offers to
# install it, and as a last resort falls back to a self-contained venv under
# ~/.local/share/fcrypt with a launcher symlinked into ~/.local/bin.
#
# Usage:
#   ./install.sh            # install (or upgrade)
#   ./install.sh --uninstall
#
set -euo pipefail

APP="fcrypt"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/$APP"
BIN_DIR="$HOME/.local/bin"

c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }
c_red() { printf '\033[1;31m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

ensure_path_hint() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            c_yellow "Note: $BIN_DIR is not on your PATH."
            info "Add this line to your ~/.bashrc or ~/.profile, then restart your shell:"
            info '    export PATH="$HOME/.local/bin:$PATH"'
            ;;
    esac
}

uninstall() {
    c_yellow "Uninstalling $APP ..."
    if have pipx && pipx list 2>/dev/null | grep -q "fcrypt-tui"; then
        pipx uninstall fcrypt-tui || true
    fi
    if [ -d "$VENV_HOME" ]; then
        rm -rf "$VENV_HOME"
        info "Removed $VENV_HOME"
    fi
    if [ -L "$BIN_DIR/$APP" ]; then
        rm -f "$BIN_DIR/$APP"
        info "Removed $BIN_DIR/$APP"
    fi
    c_green "Uninstalled."
    exit 0
}

install_with_pipx() {
    c_green "Installing $APP with pipx (isolated, no system conflicts)..."
    # --force lets this double as an upgrade.
    pipx install --force "$PKG_DIR"
    pipx ensurepath >/dev/null 2>&1 || true
    c_green "Done. Run:  $APP"
}

install_with_venv() {
    c_green "Installing $APP into a dedicated virtualenv (isolated)..."
    local py
    py="$(command -v python3)"
    rm -rf "$VENV_HOME"
    "$py" -m venv "$VENV_HOME"
    "$VENV_HOME/bin/pip" install --upgrade pip >/dev/null
    "$VENV_HOME/bin/pip" install "$PKG_DIR"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_HOME/bin/$APP" "$BIN_DIR/$APP"
    info "Linked $BIN_DIR/$APP -> $VENV_HOME/bin/$APP"
    c_green "Done. Run:  $APP"
}

main() {
    if [ "${1:-}" = "--uninstall" ] || [ "${1:-}" = "-u" ]; then
        uninstall
    fi

    if ! have python3; then
        c_red "python3 is required but was not found. Install it with your package manager, e.g.:"
        info "  Debian/Ubuntu: sudo apt install python3 python3-venv"
        info "  Fedora:        sudo dnf install python3"
        info "  Arch:          sudo pacman -S python"
        exit 1
    fi

    if have pipx; then
        install_with_pipx
    else
        c_yellow "pipx is not installed (it's the cleanest way to install CLI apps)."
        printf "Install fcrypt using a self-contained virtualenv instead? [Y/n] "
        read -r ans || ans="y"
        case "${ans:-y}" in
            [nN]*)
                c_yellow "To install pipx:"
                info "  Debian/Ubuntu: sudo apt install pipx && pipx ensurepath"
                info "  Fedora:        sudo dnf install pipx && pipx ensurepath"
                info "  Arch:          sudo pacman -S python-pipx && pipx ensurepath"
                info "  Generic:       python3 -m pip install --user pipx && python3 -m pipx ensurepath"
                info "Then re-run ./install.sh"
                exit 0
                ;;
            *)
                install_with_venv
                ;;
        esac
    fi

    ensure_path_hint
}

main "$@"
