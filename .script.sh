#!/usr/bin/env bash

set -e

echo "[System]: Detecting environment..."

# ─────────────────────────────────────────────
# Detect OS / package manager
# ─────────────────────────────────────────────

if [ -d "/data/data/com.termux" ]; then
    echo "[System]: Termux detected"

    if ! command -v pkg >/dev/null 2>&1; then
        echo "[Error]: Termux package manager not found."
        exit 1
    fi

    if ! command -v python >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        pkg update -y
        pkg install python -y
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python"

elif command -v apt-get >/dev/null 2>&1; then
    echo "[System]: Debian/Ubuntu-based Linux detected"

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python3"

elif command -v dnf >/dev/null 2>&1; then
    echo "[System]: Fedora/RHEL-based Linux detected"

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        sudo dnf install -y python3 python3-pip
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python3"

elif command -v pacman >/dev/null 2>&1; then
    echo "[System]: Arch Linux detected"

    if ! command -v python >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        sudo pacman -Sy --noconfirm python python-pip
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python"

elif command -v apk >/dev/null 2>&1; then
    echo "[System]: Alpine Linux detected"

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        sudo apk add python3 py3-pip
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python3"

elif command -v zypper >/dev/null 2>&1; then
    echo "[System]: openSUSE detected"

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[System]: Installing Python..."
        sudo zypper install -y python3 python3-pip
    else
        echo "[System]: Python is already installed"
    fi

    PYTHON="python3"

else
    echo "[Error]: Unsupported operating system or package manager."
    exit 1
fi


# ─────────────────────────────────────────────
# Check Git
# ─────────────────────────────────────────────

if ! command -v git >/dev/null 2>&1; then
    echo "[System]: Git is not installed."

    if [ -d "/data/data/com.termux" ]; then
        pkg install git -y
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y git
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y git
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm git
    elif command -v apk >/dev/null 2>&1; then
        sudo apk add git
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y git
    fi
fi


# ─────────────────────────────────────────────
# Clone Boost Manager
# ─────────────────────────────────────────────

REPO="https://github.com/featherrz/Discord-Boost-Bot"
DIR="Discord-Boost-Bot"

if [ -d "$DIR" ]; then
    echo "[System]: Repository already exists."
    cd "$DIR"
else
    echo "[System]: Cloning Boost Manager..."
    git clone "$REPO"
    cd "$DIR"
fi


# ─────────────────────────────────────────────
# Start
# ─────────────────────────────────────────────

echo
echo "[System]: Installation complete! ✅"
echo "[System]: Starting Boost Manager..."
echo

"$PYTHON" main.py
