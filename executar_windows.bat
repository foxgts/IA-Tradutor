@echo off
title Kitsune-Translate
cd /d "%~dp0"

echo ============================================
echo   Kitsune-Translate - Iniciando...
echo ============================================
echo.

:: Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [..] Python nao encontrado. Instalando via winget...
    echo.
    winget install -e --id Python.Python.3.12 --accept-package-agreements --silent
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao instalar Python.
        echo Instale manualmente: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo Python instalado. Reinicie o terminal e execute novamente.
    pause
    exit /b 0
)
python --version
echo.

:: Ambiente virtual
if not exist "venv" (
    echo [..] Criando ambiente virtual...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo Ambiente virtual criado.
    echo.
)

call venv\Scripts\activate.bat
echo [OK] Ambiente virtual ativado

:: Dependencias
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas
echo.

:: Iniciar servidor
echo ============================================
echo   Servidor: http://localhost:5000
echo   Parar: Ctrl+C
echo ============================================
echo.

python app.py

pause
