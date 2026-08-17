@echo off
setlocal enabledelayedexpansion
REM Run the full CapCut assembly kit pipeline on Windows.
REM Requires Python 3 and FFmpeg (both ffmpeg.exe and ffprobe.exe) on PATH.

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ERROR: ffmpeg was not found on PATH. Install FFmpeg and re-run.
    exit /b 1
)
where ffprobe >nul 2>nul
if errorlevel 1 (
    echo ERROR: ffprobe was not found on PATH. Install FFmpeg and re-run.
    exit /b 1
)

set SCRIPT_DIR=%~dp0

for %%S in (
    00_scan_media.py
    01_build_media_map.py
    02_make_timeline_clips.py
    03_build_timeline_voiceover.py
    04_build_preview.py
    05_build_captions.py
    06_write_reports.py
) do (
    echo.
    echo ========================================================================
    echo RUNNING %%S
    echo ========================================================================
    python "%SCRIPT_DIR%%%S"
    if errorlevel 1 (
        echo.
        echo %%S failed. Stopping.
        exit /b 1
    )
)

echo.
echo ========================================================================
echo PIPELINE COMPLETE
echo ========================================================================
echo Read 04_output\04_reports\capcut_import_steps.txt for what to do next.
endlocal
