@echo off
cd /d "%~dp0"

:: Criar venv se nao existe
if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
    echo Instalando dependencias...
    .venv\Scripts\pip.exe install -r requirements.txt
)

:: Verificar Node.js (necessario para YouTube)
where node.exe >nul 2>&1
if errorlevel 1 (
    echo Node.js nao encontrado. Necessario para downloads do YouTube.
    echo Instalando Node.js via winget...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    echo Node.js instalado. Reinicie este script.
    pause
    exit /b
)

start "" /B .venv\Scripts\pythonw.exe app.py
