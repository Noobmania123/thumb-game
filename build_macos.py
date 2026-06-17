"""Build a standalone macOS app for Apple Silicon Macs with PyInstaller.

Usage:
    python build_macos.py

Run this script on an Apple Silicon Mac (arm64/aarch64) to create:
    dist/ThumbDriveRacer.app
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "ThumbDriveRacer"


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _install_build_dependencies() -> None:
    # Keep packaging tooling fresh and force wheels so Apple Silicon does not try
    # to compile pygame/SDL from source during a normal app build.
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--only-binary=:all:",
            "-r",
            "requirements.txt",
            "pyinstaller",
        ]
    )


def _warn_if_not_apple_silicon() -> None:
    system = platform.system()
    machine = platform.machine().lower()
    if system != "Darwin":
        print("Warning: macOS apps must be built on macOS. This script is intended for Apple Silicon Macs.")
        return
    if machine not in {"arm64", "aarch64"}:
        print(f"Warning: this Mac reports '{machine}', not Apple Silicon arm64.")


def main() -> int:
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Using Python {py_ver} ({sys.executable})")
    _warn_if_not_apple_silicon()

    try:
        _install_build_dependencies()
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--windowed",
                "--name",
                APP_NAME,
                "main.py",
            ]
        )
    except subprocess.CalledProcessError as exc:
        print(f"\nBuild failed (exit code {exc.returncode}).")
        print(
            "\nTip: Use a native Apple Silicon Python from python.org or Homebrew, "
            "then rerun: python build_macos.py"
        )
        return exc.returncode

    app_path = PROJECT_ROOT / "dist" / f"{APP_NAME}.app"
    print("\nBuild complete.")
    print(f"macOS app path: {app_path}")
    print("Copy the .app to your Applications folder or a USB drive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
