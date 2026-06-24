#!/bin/bash

# ============================================================
#  Executar - Kitsune-Translate (Linux)
# ============================================================

cd "$(dirname "$0")" || exit 1

echo "============================================"
echo "  Kitsune-Translate - Iniciando..."
echo "============================================"
echo ""

# Verificar Python
PYTHON_CMD=""

for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[..] Python nao encontrado. Instalando..."

    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3 python3-venv python3-pip && PYTHON_CMD="python3"
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-venv python3-pip && PYTHON_CMD="python3"
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm python python-pip && PYTHON_CMD="python"
    elif command -v zypper &> /dev/null; then
        sudo zypper install -y python3 python3-venv python3-pip && PYTHON_CMD="python3"
    else
        echo "[ERRO] Gerenciador de pacotes nao reconhecido."
        echo "Instale o Python manualmente: https://python.org"
        exit 1
    fi

    if [ -z "$PYTHON_CMD" ] || ! command -v "$PYTHON_CMD" &> /dev/null; then
        echo "[ERRO] Falha ao instalar Python."
        exit 1
    fi
    echo "Python instalado."
    echo ""
fi

$PYTHON_CMD --version
echo ""

# Ambiente virtual
if [ ! -d "venv" ]; then
    echo "[..] Criando ambiente virtual..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERRO] Falha ao criar ambiente virtual."
        exit 1
    fi
    echo "Ambiente virtual criado."
    echo ""
fi

source venv/bin/activate
echo "[OK] Ambiente virtual ativado"

# Dependencias
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "[ERRO] Falha ao instalar dependencias."
    exit 1
fi
echo "[OK] Dependencias instaladas"
echo ""

# Servidor
echo "============================================"
echo "  Servidor: http://localhost:5000"
echo "  Parar: Ctrl+C"
echo "============================================"
echo ""

$PYTHON_CMD app.py
