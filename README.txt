Video Clip Maker — Setup & Build Instructions
===============================================

RUNNING DIRECTLY (for testing)
------------------------------
1. Install Python 3.x from https://python.org
2. Open a terminal in this folder
3. Run:  python clip_maker.py
4. The GUI will open — pick a video, set times, click Start

Note: ffmpeg must be installed and on your PATH, or place the ffmpeg
binary (ffmpeg.exe on Windows, ffmpeg on Mac/Linux) in this folder.


BUILDING A STANDALONE .EXE (Windows)
-------------------------------------
1. Install Python 3.x (check "Add to PATH" during install)
2. Install PyInstaller:
       pip install pyinstaller
3. Download a static ffmpeg build:
       https://www.gyan.dev/ffmpeg/builds/  (get the "essentials" zip)
4. Extract ffmpeg.exe and place it in this folder (next to clip_maker.py)
5. Double-click build.bat  (or run it from a terminal)
6. The finished app will be at:  dist\VideoClipMaker.exe
7. Copy that .exe to any Windows machine — no install needed


USAGE
-----
- Video File:   Click Browse to pick .mp4, .avi, .mov, .mkv, etc.
- Start/End:    Use H:MM:SS format (e.g., 0:22:29 to 0:31:38)
- Slowdown %:   0 = normal speed, 50 = half speed, etc.
- Output Name:  The clip saves to your Desktop as <name>.mp4
- Click Start and wait for "Done!" in the status bar.
