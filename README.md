# Thumb Drive Racer (Pygame)

A pseudo-3D **2D racing game** made in Python + Pygame, designed to run from a USB drive and package to a standalone Windows `.exe`.

## Features
- Pseudo-3D retro road rendering (classic sim illusion).
- Track with **strong turns**, elevation changes, and visible **wall barriers**.
- Crash physics on wall impact (bounce + speed penalty + recovery timer).
- **Race mode** with 3-lap win condition and start countdown.
- Multiplayer:
  - Single player
  - Local multiplayer (2 players on one keyboard)
  - Online multiplayer (simple UDP host/join)
- Fast mode switching in-game (TAB / F1-F4) without restarting.
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

### Global
- **TAB:** cycle mode (single → local → online host → online join)
- **F1/F2/F3/F4:** jump directly to mode
- **R:** toggle/restart race mode

## Game modes
```bash
# Start in single-player free drive
python main.py --mode single

# Start in local multiplayer
python main.py --mode local

# Start as online host
python main.py --mode online-host --port 50555

# Start as online client
python main.py --mode online-join --host <HOST_IP> --port 50555

# Start with race mode enabled immediately
python main.py --mode single --race
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
