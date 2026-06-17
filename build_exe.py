"""Build a standalone Windows executable with PyInstaller.

Usage:
    python build_exe.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _install_build_dependencies() -> None:
    # Keep packaging tooling fresh and force wheel-only installs for game deps.
    # Wheel-only avoids accidental source builds (common failure on new Python versions).
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


def main() -> int:
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Using Python {py_ver} ({sys.executable})")

    try:
        _install_build_dependencies()
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--onefile",
                "--windowed",
                "--name",
                "ThumbDriveRacer",
                "main.py",
            ]
        )
    except subprocess.CalledProcessError as exc:
        print(f"\nBuild failed (exit code {exc.returncode}).")
        print(
            "\nTip: If dependency install failed, ensure your Python version has prebuilt "
            "wheels for the selected pygame package in requirements.txt."
        )
        return exc.returncode

    exe_path = PROJECT_ROOT / "dist" / "ThumbDriveRacer.exe"
    print("\nBuild complete.")
    print(f"EXE path: {exe_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
