#!/bin/bash

# ============================================================
#  Auto-iniciar - Kitsune-Translate (Linux)
# ============================================================
#  Configura o sistema para iniciar automaticamente o
#  Kitsune-Translate quando o computador ligar.
# ============================================================
#  Cria servico systemd para iniciar o tradutor
#  automaticamente quando o computador ligar.
#
#  Uso:
#    ./auto_iniciar_linux.sh install    - Instala o servico
#    ./auto_iniciar_linux.sh remove     - Remove o servico
#    ./auto_iniciar_linux.sh status     - Verifica status
#    ./auto_iniciar_linux.sh logs       - Mostra logs
# ============================================================

SERVICE_NAME="tradutor-legendas"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_CMD=""

# -----------------------------------------------------------
# INSTALL
# -----------------------------------------------------------
install_service() {
    echo "============================================"
    echo "  Instalar servico: ${SERVICE_NAME}"
    echo "============================================"
    echo ""

    # Verificar diretorio
    if [ ! -f "${SCRIPT_DIR}/app.py" ]; then
        echo "[ERRO] app.py nao encontrado em ${SCRIPT_DIR}"
        echo "Execute o script da pasta do projeto."
        exit 1
    fi
    echo "[OK] Projeto encontrado"
    echo ""

    # Verificar/instalar Python
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
    fi
    echo "[OK] $($PYTHON_CMD --version 2>&1)"
    echo ""

    # Criar ambiente virtual se nao existir
    if [ ! -d "${SCRIPT_DIR}/venv" ]; then
        echo "[..] Criando ambiente virtual..."
        cd "${SCRIPT_DIR}" && $PYTHON_CMD -m venv venv
        if [ $? -ne 0 ]; then
            echo "[ERRO] Falha ao criar ambiente virtual."
            exit 1
        fi
        echo "Ambiente virtual criado."
    fi
    echo "[OK] Ambiente virtual encontrado"
    echo ""

    # Instalar dependencias
    echo "[..] Instalando dependencias..."
    source "${SCRIPT_DIR}/venv/bin/activate"
    pip install -r "${SCRIPT_DIR}/requirements.txt" --quiet
    if [ $? -ne 0 ]; then
        echo "[ERRO] Falha ao instalar dependencias."
        exit 1
    fi
    deactivate
    echo "[OK] Dependencias instaladas"
    echo ""

    # Verificar Ollama
    OLLAMA_SERVICE=false
    if systemctl is-active --quiet ollama 2>/dev/null; then
        OLLAMA_SERVICE=true
        echo "[OK] Ollama em execucao como servico"
    elif command -v ollama &> /dev/null; then
        echo "[ATENCAO] Ollama instalado mas nao como servico systemd."
        echo "         Execute: curl -fsSL https://ollama.com/install.sh | sh"
    else
        echo "[ATENCAO] Ollama nao encontrado."
        echo "         Instale e configure antes de usar o tradutor."
    fi
    echo ""

    # Montar service
    OLLAMA_DEPENDS=""
    OLLAMA_AFTER=""
    if [ "$OLLAMA_SERVICE" = true ]; then
        OLLAMA_DEPENDS="Requires=ollama.service"
        OLLAMA_AFTER="After=ollama.service"
    fi

    echo "[..] Criando servico systemd..."
    sudo tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=Kitsune-Translate
After=network.target ${OLLAMA_AFTER}
${OLLAMA_DEPENDS}

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${SCRIPT_DIR}
Environment=PATH=${SCRIPT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -ne 0 ]; then
        echo "[ERRO] Falha ao criar servico."
        exit 1
    fi

    sudo systemctl daemon-reload
    sudo systemctl enable "${SERVICE_NAME}"
    sudo systemctl start "${SERVICE_NAME}"

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "[OK] Servico instalado e em execucao"
    else
        echo "[ATENCAO] Servico instalado mas pode nao ter iniciado."
        echo "         Verifique: sudo systemctl status ${SERVICE_NAME}"
    fi
    echo ""

    echo "============================================"
    echo "  Instalacao concluida!"
    echo ""
    echo "  URL: http://localhost:5000"
    echo ""
    echo "  Comandos:"
    echo "    sudo systemctl status ${SERVICE_NAME}"
    echo "    sudo systemctl stop ${SERVICE_NAME}"
    echo "    sudo systemctl start ${SERVICE_NAME}"
    echo "    sudo systemctl restart ${SERVICE_NAME}"
    echo "    sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "  Remover: ./auto_iniciar_linux.sh remove"
    echo "============================================"
}

# -----------------------------------------------------------
# REMOVE
# -----------------------------------------------------------
remove_service() {
    if [ ! -f "${SERVICE_FILE}" ]; then
        echo "Servico ${SERVICE_NAME} nao encontrado."
        exit 0
    fi

    echo "Removendo servico ${SERVICE_NAME}..."
    sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null
    sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null
    sudo rm -f "${SERVICE_FILE}"
    sudo systemctl daemon-reload
    echo "Servico removido."
}

# -----------------------------------------------------------
# STATUS
# -----------------------------------------------------------
show_status() {
    if [ -f "${SERVICE_FILE}" ]; then
        systemctl status "${SERVICE_NAME}" 2>/dev/null
    else
        echo "Servico ${SERVICE_NAME} nao instalado."
        echo "Instale com: ./auto_iniciar_linux.sh install"
    fi
}

# -----------------------------------------------------------
# LOGS
# -----------------------------------------------------------
show_logs() {
    if [ -f "${SERVICE_FILE}" ]; then
        journalctl -u "${SERVICE_NAME}" -f
    else
        echo "Servico ${SERVICE_NAME} nao instalado."
        exit 1
    fi
}

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
case "${1:-}" in
    install) install_service ;;
    remove)  remove_service ;;
    status)  show_status ;;
    logs)    show_logs ;;
    *)
        echo "Uso: $0 {install|remove|status|logs}"
        echo ""
        echo "  install   Instala servico de auto-inicio"
        echo "  remove    Remove o servico"
        echo "  status    Verifica status do servico"
        echo "  logs      Mostra logs em tempo real"
        ;;
esac
