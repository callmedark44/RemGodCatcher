@echo off
echo Building RemGodCatcher for Windows...
pip install pyinstaller
pip install -r requirements.txt
pyinstaller --onefile --name RemGodCatcher.exe --add-data "web;web" --add-data "workers;workers" --add-data "database;database" --add-data "shared.py;." --collect-all rule34Py --hidden-import flask_socketio --hidden-import engineio.async_drivers.threading Rem_catcher.py
echo Done. Binary at dist\RemGodCatcher.exe
pause
