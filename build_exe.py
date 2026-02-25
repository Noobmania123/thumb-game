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


def main() -> int:
    try:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller"])
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
        return exc.returncode

    exe_path = PROJECT_ROOT / "dist" / "ThumbDriveRacer.exe"
    print("\nBuild complete.")
    print(f"EXE path: {exe_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
