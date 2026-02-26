# Thumb Drive Racer (Pygame)

A pseudo-3D **2D racing game** made in Python + Pygame, designed to run from a USB drive and package to a standalone Windows `.exe`.

## Features
- Barriers and trees are rendered as actual projected 3D geometry so they remain visible.
- Actual 3D-style road/world rendering using camera-space polygon projection (in Pygame).
- Track with strong turns, elevation changes, **high-visibility barrier walls**, and dense roadside trees.
- Crash physics on wall impact with speed-based outcomes (stall or explosion).
- Race mode with 3-lap win condition and start countdown.
- Speed display is capped/tuned to top out at **300 km/h**.
- Multiplayer:
  - Single player
  - Local multiplayer (2 players on one keyboard)
  - Online multiplayer (simple UDP host/join)
- Fast mode switching in-game (TAB / F1-F4) without restarting.
- Performance profiles designed for low-power systems (Latitude 3120 / Pentium / older i3).
- Windows `.exe` build script in Python (`build_exe.py`).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py --performance auto
```

## Controls
### Player 1
- Accelerate: `W` or `Up`
- Brake: `S` or `Down`
- Rotate: `A/D` or `Left/Right`

### Player 2 (local mode)
- Accelerate: `I`
- Brake: `K`
- Rotate: `J/L`

### Global
- `TAB`: cycle mode (single → local → online host → online join)
- `F1/F2/F3/F4`: jump directly to mode
- `R`: hard restart after a crash/explosion (or normal restart)
- `T`: toggle race mode
- `F8`: cycle performance preset while running

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

## Recommended for Latitude 3120 / Pentium / i3 10th gen
```bash
# Best first try for low-end CPUs
python main.py --performance ultra-low

# Auto picks based on CPU (Pentium/Celeron => ultra-low)
python main.py --performance auto
```

## Handling fixes included
- Added steering assist / curve compensation so A/D turning does not shove the car into barriers on bends.
- Reduced lateral drift and tuned heading recenter for more controllable rotation steering.

## Responsiveness fixes included
- Software SDL render driver default to avoid some Intel iGPU black-screen/driver issues.
- Very low default workload in `ultra-low` profile (640x360, shorter draw distance, reduced effects).
- Runtime adaptive downgrade if frame-time stays too high.
- Frame delta clamp to avoid long-frame simulation stalls.

## Build Windows EXE
On Windows, run:

```bash
python build_exe.py
```

Output:
- `dist\ThumbDriveRacer.exe`

## Python version note
- For Python 3.12 and older, this project installs `pygame`.
- For Python 3.13+, this project installs `pygame-ce` (compatible `import pygame`).
- The build script uses wheel-only dependency installs to avoid source-build failures.

## Online note
For online play across devices, allow UDP port `50555` (or your chosen port) in firewall settings.


## If you still see black screen / not responding
- Run with: `python main.py --performance ultra-low`
- Wait for the loading bar to reach 100%; it now updates in steps.
- The game now reuses loading fonts and updates only on percent changes to avoid startup stalls.
- If packaged as EXE, run it from a terminal once to capture any fatal error output.


## Crash outcomes by speed
- **High-speed wall hit:** car explodes and is disabled.
- **Lower-speed wall hit:** car stalls and is disabled.
- In both cases, press **R** to restart.
