@echo off
REM Build a standalone .exe for Windows using PyInstaller
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name ThumbDriveRacer main.py

echo.
echo Build complete. EXE is in dist\ThumbDriveRacer.exe
pause
