# Thumb Drive Racer (Pygame)

A pseudo-3D **2D racing game** made in Python + Pygame, designed to run from a USB drive and package to a standalone Windows `.exe`.

## Features
- Pseudo-3D retro road rendering (classic sim illusion).
- Real racetrack boundaries with **visible barriers/walls**.
- **Crash physics** on wall impact (bounce + speed penalty + short recovery).
- Multiplayer:
  - **Single player**
  - **Local multiplayer** (2 players on one keyboard)
  - **Online multiplayer** (simple UDP host/join)
- Windows `.exe` build script in Python (`build_exe.py`).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Controls
### Player 1
- **Accelerate:** `W` or `Up`
- **Brake:** `S` or `Down`
- **Steer:** `A/D` or `Left/Right`

### Player 2 (local mode)
- **Accelerate:** `I`
- **Brake:** `K`
- **Steer:** `J/L`

## Game modes
```bash
# Single player
python main.py --mode single

# Local multiplayer (same keyboard)
python main.py --mode local

# Online host (machine A)
python main.py --mode online-host --port 50555

# Online join (machine B)
python main.py --mode online-join --host <HOST_IP> --port 50555
```

> For online play across devices, allow UDP port `50555` (or your chosen port) in firewall settings.

## Build Windows EXE
On Windows, run:

```bash
python build_exe.py
```

Output:
- `dist\ThumbDriveRacer.exe`

## Python version note
- For **Python 3.12 and older**, this project installs `pygame`.
- For **Python 3.13+**, this project installs `pygame-ce` (compatible `import pygame`).
- The build script uses wheel-only dependency installs to avoid source-build failures.

## Latitude 3120 performance tips
- Keep laptop on AC power + High Performance mode.
- If FPS is low, reduce `DRAW_DISTANCE` in `main.py` from `220` to ~`150`.
