@echo off
python -V | findstr /R /C:"3\.5\.[0-9]*" /C:"3\.6\.[0-9]*" /C:"3\.7\.[0-9]*" /C:"3\.8\.[0-9]*" /C:"3\.9\.[0-9]*" /C:"3\.10\.[0-9]*"
if %errorlevel 0 (
    color e
    echo Starting...
    pip install -r requirements.txt
    cls
    color f
    title Discord Server Copier
    python main.py
) else (
    echo Your python version doesn't supported.
    echo discord.py 1.7.3 requiring python version from 3.5.3 to 3.10, your python is %errorlevel%
)
pause>nul