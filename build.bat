@echo off
echo Building Video Clip Maker...
echo.
echo Make sure ffmpeg.exe is in this folder before building.
echo.
pip install Pillow >nul 2>&1

pyinstaller --onefile --windowed --add-binary "ffmpeg.exe;." --name "VideoClipMaker" clip_maker.py

echo.
if exist dist\VideoClipMaker.exe (
    echo Build complete! Find VideoClipMaker.exe in the dist\ folder.
) else (
    echo Build failed. Check the output above for errors.
)
pause
