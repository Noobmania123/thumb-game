# Thumb Drive Racer (Pygame)

A lightweight pseudo-3D **2D racing game** made in Python + Pygame.
It is designed to be simple enough to run from a USB thumb drive and can be packaged as a standalone `.exe`.

## Features
- Pseudo-3D "classic sim" road rendering (old-school style illusion).
- Curved roads and rolling hills.
- Keyboard controls (WASD / Arrow keys).
- Simple car + speed HUD.
- Windows `.exe` build script (Python).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Controls
- **Accelerate:** `W` / `Up`
- **Brake:** `S` / `Down`
- **Steer left/right:** `A` `D` / `Left` `Right`

## Build Windows EXE
On Windows, run:

```bash
python build_exe.py
```

Output:
- `dist\ThumbDriveRacer.exe`

Then copy that EXE (and optionally a `README.txt`) to your USB drive.

## Latitude 3120 notes
- Use `--onefile` build (already set) for easiest USB deployment.
- If performance is low, reduce `DRAW_DISTANCE` in `main.py` from `220` to around `150`.
- Keep the laptop on AC power and use High Performance power mode for smoother FPS.

### Python version note
- For **Python 3.12 and older**, this project installs `pygame`.
- For **Python 3.13+**, this project installs `pygame-ce` (compatible `import pygame`).
- The build script uses wheel-only dependency installs to avoid source-build failures on Windows.
