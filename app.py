# =====================================================
# IMPORTS
# =====================================================

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    send_file
)

from pathlib import Path
from werkzeug.utils import secure_filename

import sqlite3
import requests
import logging
import pysrt
import threading
import time
import math

from datetime import datetime

# =====================================================
# CONFIGURAÇÃO
# =====================================================

APP_NAME = "Kitsune-Translate"

BASE_DIR = Path(__file__).parent

UPLOAD_DIR = BASE_DIR / "uploads"
TRANSLATED_DIR = BASE_DIR / "translated"
TEMP_DIR = BASE_DIR / "temp"
DATABASE_DIR = BASE_DIR / "database"
LOG_DIR = BASE_DIR / "logs"

DB_FILE = DATABASE_DIR / "history.db"
LOG_FILE = LOG_DIR / "translator.log"

OLLAMA_URL = "http://localhost:11434"

ALLOWED_EXTENSIONS = {"srt"}

BATCH_SIZE = 15

# =====================================================
# FLASK
# =====================================================

app = Flask(__name__)

# =====================================================
# ESTADO GLOBAL
# =====================================================

translation_state = {
    "running": False,
    "phase": "idle",

    "progress": 0,

    "current": 0,
    "total": 0,

    "current_batch": 0,
    "total_batches": 0,

    "eta": "--",

    "filename": "",
    "output_file": "",
    "model": "",

    "preview": [],

    "queue": [],
    "queue_current": 0,
    "queue_total": 0,
    "queue_filename": ""
}

# =====================================================
# PASTAS
# =====================================================

def create_folders():

    folders = [
        UPLOAD_DIR,
        TRANSLATED_DIR,
        TEMP_DIR,
        DATABASE_DIR,
        LOG_DIR
    ]

    for folder in folders:
        folder.mkdir(
            parents=True,
            exist_ok=True
        )

# =====================================================
# LOGS
# =====================================================

def setup_logging():

    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

# =====================================================
# SQLITE
# =====================================================

def init_database():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS translations (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            filename TEXT,
            output_file TEXT,

            model TEXT,

            total_subtitles INTEGER,
            translated_subtitles INTEGER,

            status TEXT,

            started_at TEXT,
            finished_at TEXT
        )
    """)

    conn.commit()
    conn.close()

# =====================================================
# OLLAMA
# =====================================================

def ollama_online():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )

        return response.status_code == 200

    except Exception:

        return False

def get_ollama_models():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )

        if response.status_code != 200:
            return []

        data = response.json()

        return [
            model.get("name")
            for model in data.get("models", [])
        ]

    except Exception as e:

        logging.error(
            f"Erro modelos Ollama: {e}"
        )

        return []

def ollama_chat(model, prompt):

    try:

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content":
                    "Você é um assistente de tradução especializado em legendas. "
                    "Traduza textos para português brasileiro de forma precisa e natural. "
                    "Responda APENAS com as traduções solicitadas. "
                    "NÃO repita instruções, regras, formatação do prompt ou o texto original. "
                    "NÃO adicione explicações, comentários ou observações."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120
        )

        if response.status_code != 200:

            raise Exception(
                f"Ollama retornou {response.status_code}"
            )

        data = response.json()

        return (
            data
            .get("message", {})
            .get("content", "")
            .strip()
        )

    except Exception as e:

        logging.exception(
            f"Erro Ollama: {e}"
        )

        raise

# =====================================================
# UTILITÁRIOS
# =====================================================

def allowed_file(filename):

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return extension in ALLOWED_EXTENSIONS

def split_into_batches(items, batch_size=BATCH_SIZE):

    batches = []

    for i in range(
        0,
        len(items),
        batch_size
    ):
        batches.append(
            items[i:i + batch_size]
        )

    return batches

def format_eta(seconds):

    minutes = int(seconds // 60)

    seconds = int(seconds % 60)

    return f"{minutes}m {seconds}s"

# =====================================================
# UPLOAD SRT
# =====================================================

def load_subtitle_file(file_path):

    subtitles = pysrt.open(
        str(file_path),
        encoding="utf-8"
    )

    return subtitles

def count_subtitles(file_path):

    subtitles = load_subtitle_file(
        file_path
    )

    return len(subtitles)

# =====================================================
# TRADUÇÃO
# =====================================================

def build_translation_prompt(texts):

    numbered_lines = []

    for idx, text in enumerate(texts, start=1):

        clean_text = text.replace("\n", " <br> ").strip()

        numbered_lines.append(
            f"[{idx}] {clean_text}"
        )

    joined_text = "\n".join(numbered_lines)

    prompt = f"""Abaixo estão as linhas de legenda para traduzir.

{joined_text}

Traduza cada linha para português brasileiro. Preserve a ordem e a numeração [n]. Preserve o marcador <br> como separador de linhas dentro de cada legenda. NÃO repita o texto original. NÃO adicione explicações, comentários ou observações. Responda APENAS com as traduções numeradas.

Exemplo:
[1] Hello <br> How are you?
[1] Olá <br> Como vai?"""

    return prompt.strip()

def parse_translation_response(
    response_text,
    expected_count
):

    lines = []

    for line in response_text.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("["):
            pos = line.find("]")

            if pos != -1:
                line = line[pos + 1:].strip()

        lines.append(line)

    while len(lines) < expected_count:

        lines.append("")

    return lines[:expected_count]

def translate_batch(
    batch,
    model
):

    texts = []

    for subtitle in batch:

        texts.append(
            subtitle.text.strip()
        )

    prompt = build_translation_prompt(
        texts
    )

    response = ollama_chat(
        model,
        prompt
    )

    translations = (
        parse_translation_response(
            response,
            len(batch)
        )
    )

    for i in range(len(translations)):
        translations[i] = (
            translations[i]
            .replace(" <br> ", "\n")
            .replace("<br> ", "\n")
            .replace(" <br>", "\n")
            .replace("<br>", "\n")
        )

    return translations

# =====================================================
# SALVAMENTO
# =====================================================

def save_partial_file(
    subtitles,
    output_path
):

    subtitles.save(
        str(output_path),
        encoding="utf-8"
    )

def create_output_name(
    original_name
):

    stem = Path(
        original_name
    ).stem

    return f"{stem}.pt-BR.srt"

# =====================================================
# HISTÓRICO
# =====================================================

def add_history_record(
    filename,
    output_file,
    model,
    total_subtitles,
    translated_subtitles,
    status
):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO translations (

            filename,
            output_file,
            model,

            total_subtitles,
            translated_subtitles,

            status,

            started_at,
            finished_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            output_file,
            model,

            total_subtitles,
            translated_subtitles,

            status,

            datetime.now().isoformat(),
            datetime.now().isoformat()
        )
    )

    conn.commit()
    conn.close()

def get_history():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            filename,
            output_file,
            model,
            translated_subtitles,
            status,
            finished_at
        FROM translations
        ORDER BY id DESC
        LIMIT 20
        """
    )

    rows = cursor.fetchall()

    conn.close()

    history = []

    for row in rows:

        history.append({
            "filename": row[0],
            "output_file": row[1],
            "model": row[2],
            "translated": row[3],
            "status": row[4],
            "finished_at": row[5]
        })

    return history

# =====================================================
# WORKER
# =====================================================

def translate_single_file(
    file_path,
    model
):

    try:

        start_time = time.time()

        translation_state["phase"] = "loading"
        translation_state["model"] = model
        translation_state["filename"] = Path(file_path).name

        subtitles = load_subtitle_file(
            file_path
        )

        total_subtitles = len(
            subtitles
        )

        batches = split_into_batches(
            subtitles,
            BATCH_SIZE
        )

        total_batches = len(
            batches
        )

        translation_state["total"] = (
            total_subtitles
        )

        translation_state[
            "total_batches"
        ] = total_batches

        partial_name = (
            Path(file_path).stem
            + ".partial.srt"
        )

        partial_file = (
            TEMP_DIR /
            partial_name
        )

        translated_count = 0

        for batch_index, batch in enumerate(
            batches,
            start=1
        ):

            translation_state[
                "phase"
            ] = "translating"

            translated_texts = (
                translate_batch(
                    batch,
                    model
                )
            )

            for subtitle, translated_text in zip(
                batch,
                translated_texts
            ):

                subtitle.text = (
                    translated_text
                )

                translated_count += 1

                translation_state[
                    "current"
                ] = translated_count

            save_partial_file(
                subtitles,
                partial_file
            )

            translation_state[
                "current_batch"
            ] = batch_index

            progress = (
                translated_count
                / total_subtitles
            ) * 100

            translation_state[
                "progress"
            ] = round(progress)

            preview_items = []

            for item in batch[-5:]:

                preview_items.append(
                    item.text
                )

            translation_state[
                "preview"
            ] = preview_items

            elapsed = (
                time.time()
                - start_time
            )

            average_batch = (
                elapsed / batch_index
            )

            remaining = (
                total_batches
                - batch_index
            )

            eta = (
                average_batch
                * remaining
            )

            translation_state[
                "eta"
            ] = format_eta(
                eta
            )

        output_name = (
            create_output_name(
                Path(file_path).name
            )
        )

        output_file = (
            TRANSLATED_DIR
            / output_name
        )

        subtitles.save(
            str(output_file),
            encoding="utf-8"
        )

        translation_state[
            "output_file"
        ] = output_name

        add_history_record(
            Path(file_path).name,
            output_name,
            model,
            total_subtitles,
            translated_count,
            "completed"
        )

        if partial_file.exists():
            partial_file.unlink()

        translation_state[
            "phase"
        ] = "completed"

        translation_state[
            "progress"
        ] = 100

    except Exception as e:

        logging.exception(
            f"Erro tradução: {e}"
        )

        translation_state[
            "phase"
        ] = "error"

# =====================================================
# FILA DE TRADUÇÃO
# =====================================================

def process_queue():

    translation_state["running"] = True

    while translation_state["queue"]:

        item = translation_state["queue"][0]

        file_path = item["file_path"]
        model = item["model"]

        position = (
            translation_state["queue_total"]
            - len(translation_state["queue"])
            + 1
        )

        translation_state[
            "queue_current"
        ] = position

        translation_state[
            "queue_filename"
        ] = item["filename"]

        translate_single_file(
            file_path,
            model
        )

        translation_state["queue"].pop(0)

    translation_state["running"] = False

    translation_state["phase"] = "idle"

    translation_state["queue"] = []

    translation_state[
        "queue_current"
    ] = 0

    translation_state[
        "queue_total"
    ] = 0

    translation_state[
        "queue_filename"
    ] = ""

# =====================================================
# ROTAS
# =====================================================

@app.route("/")
def index():

    models = get_ollama_models()

    return render_template(
        "index.html",
        ollama_online=ollama_online(),
        models=models
    )

@app.route("/api/status")
def api_status():

    return jsonify({
        "online": ollama_online(),
        "models": get_ollama_models(),
        "server_time": datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )
    })

@app.route("/api/progress")
def api_progress():

    return jsonify(
        translation_state
    )

@app.route("/api/history")
def api_history():

    return jsonify(
        get_history()
    )

@app.route("/api/upload", methods=["POST"])
def api_upload():

    try:

        if "files" not in request.files:

            return jsonify({
                "success": False,
                "message": "Arquivo(s) não enviado(s)."
            }), 400

        files = request.files.getlist("files")

        if not files:

            return jsonify({
                "success": False,
                "message": "Nenhum arquivo selecionado."
            }), 400

        uploaded = []

        for file in files:

            if file.filename == "":
                continue

            if not allowed_file(
                file.filename
            ):
                continue

            filename = secure_filename(
                file.filename
            )

            destination = (
                UPLOAD_DIR / filename
            )

            file.save(
                destination
            )

            total_subtitles = (
                count_subtitles(
                    destination
                )
            )

            uploaded.append({
                "filename": filename,
                "total_subtitles":
                total_subtitles
            })

            logging.info(
                f"Upload: {filename}"
            )

        if not uploaded:

            return jsonify({
                "success": False,
                "message":
                "Nenhum arquivo .srt válido enviado."
            }), 400

        return jsonify({
            "success": True,
            "files": uploaded,
            "total": len(uploaded)
        })

    except Exception as e:

        logging.exception(
            f"Upload erro: {e}"
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route(
    "/api/translate",
    methods=["POST"]
)
def api_translate():

    try:

        data = request.get_json()

        filenames = data.get(
            "filenames",
            []
        )

        if isinstance(
            filenames,
            str
        ):
            filenames = [filenames]

        model = data.get(
            "model"
        )

        if not filenames:

            return jsonify({
                "success": False,
                "message":
                "Nenhum arquivo informado."
            })

        if not model:

            return jsonify({
                "success": False,
                "message":
                "Modelo não informado."
            })

        queue = []

        for filename in filenames:

            file_path = (
                UPLOAD_DIR /
                filename
            )

            if file_path.exists():

                queue.append({
                    "filename": filename,
                    "file_path":
                    str(file_path),
                    "model": model
                })

        if not queue:

            return jsonify({
                "success": False,
                "message":
                "Nenhum arquivo encontrado."
            })

        if translation_state[
            "running"
        ]:

            translation_state[
                "queue"
            ].extend(queue)

            translation_state[
                "queue_total"
            ] = len(
                translation_state[
                    "queue"
                ]
            )

            logging.info(
                f"Adicionado {len(queue)} "
                f"arquivo(s) à fila"
            )

            return jsonify({
                "success": True,
                "total":
                len(queue),
                "message":
                "Adicionado à fila."
            })

        translation_state[
            "queue"
        ] = queue

        translation_state[
            "queue_total"
        ] = len(queue)

        translation_state[
            "queue_current"
        ] = 0

        translation_state[
            "queue_filename"
        ] = queue[0]["filename"]

        worker = threading.Thread(
            target=process_queue,
            daemon=True
        )

        worker.start()

        logging.info(
            f"Fila iniciada: "
            f"{len(queue)} arquivo(s) | {model}"
        )

        return jsonify({
            "success": True,
            "total": len(queue)
        })

    except Exception as e:

        logging.exception(
            f"Erro iniciar tradução: {e}"
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route(
    "/api/download/<filename>"
)
def api_download(filename):

    file_path = (
        TRANSLATED_DIR /
        filename
    )

    if not file_path.exists():

        return jsonify({
            "success": False,
            "message":
            "Arquivo não encontrado."
        }), 404

    return send_file(
        file_path,
        as_attachment=True
    )

@app.route(
    "/api/clear_history",
    methods=["POST"]
)
def api_clear_history():

    try:

        conn = sqlite3.connect(
            DB_FILE
        )

        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM translations"
        )

        conn.commit()
        conn.close()

        for f in UPLOAD_DIR.iterdir():

            if f.is_file():
                f.unlink()

        for f in TRANSLATED_DIR.iterdir():

            if f.is_file():
                f.unlink()

        for f in TEMP_DIR.iterdir():

            if f.is_file():
                f.unlink()

        logging.info(
            "Histórico e arquivos limpos"
        )

        return jsonify({
            "success": True,
            "message":
            "Histórico e arquivos limpos."
        })

    except Exception as e:

        logging.exception(
            f"Erro limpar histórico: {e}"
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =====================================================
# INICIALIZAÇÃO
# =====================================================

create_folders()

setup_logging()

init_database()

logging.info(
    "Sistema iniciado"
)

# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
