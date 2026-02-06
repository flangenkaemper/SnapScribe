# SnapScribe
A fast, lightweight tool to record and transcribe audio instantly using Whisper.

# Install & Run SnapScribe
Open the Releases Section on the right and choose a Version. You will find details there, e.g. on how to install/run, recommended specs, etc. 

# Development
Start of Development Section
# Requirements & Setup
Uses poetry for dependency/package management, see: https://python-poetry.org/docs/

To install poetry use:
```shell 
pipx install poetry
``` 
or 
```shell 
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```
Make sure to setup PATH & restart your IDE/Shell.

Install project packages afterwards using:
```shell 
poetry install
```

To launch SnapScribe:
```shell 
poetry run python main.py
```

For building .exe:
```shell 
poetry run pyinstaller --noconfirm --onedir --windowed --icon "assets/icon.ico" --name "SnapScribe" --add-data "assets;assets" --hidden-import="whisper" --collect-all="whisper" main.py
```
