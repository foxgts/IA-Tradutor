const statusElement =
    document.getElementById("ollamaStatus");

const modelSelect =
    document.getElementById("model");

const fileInput =
    document.getElementById("subtitleFile");

const fileInfo =
    document.getElementById("fileInfo");

const translateBtn =
    document.getElementById("translateBtn");

const progressFill =
    document.getElementById("progressFill");

const progressText =
    document.getElementById("progressText");

const subtitleCounter =
    document.getElementById("subtitleCounter");

const batchInfo =
    document.getElementById("batchInfo");

const etaElement =
    document.getElementById("eta");

const previewElement =
    document.getElementById("preview");

const historyElement =
    document.getElementById("history");

const downloadArea =
    document.getElementById("downloadArea");

const downloadLink =
    document.getElementById("downloadLink");

const queueInfo =
    document.getElementById("queueInfo");

const queueProgressFill =
    document.getElementById("queueProgressFill");

const clearHistoryBtn =
    document.getElementById("clearHistoryBtn");

let uploadedFiles = [];

async function updateStatus() {

    try {

        const response =
            await fetch("/api/status");

        const data =
            await response.json();

        if (data.online) {

            statusElement.innerHTML =
                `🟢 Online (${data.models.length} modelos)`;

            statusElement.className =
                "success";

        } else {

            statusElement.innerHTML =
                "🔴 Ollama Offline";

            statusElement.className =
                "error";
        }

    } catch (error) {

        console.error(error);

        statusElement.innerHTML =
            "🔴 Erro de comunicação";

        statusElement.className =
            "error";
    }
}

async function uploadFiles() {

    const files =
        fileInput.files;

    if (!files || files.length === 0) {
        return;
    }

    fileInfo.innerHTML =
        "📖 Enviando arquivos...";

    const formData =
        new FormData();

    for (const file of files) {
        formData.append(
            "files",
            file
        );
    }

    try {

        const response =
            await fetch(
                "/api/upload",
                {
                    method: "POST",
                    body: formData
                }
            );

        const data =
            await response.json();

        if (!data.success) {

            fileInfo.innerHTML =
                "❌ " + data.message;

            return;
        }

        uploadedFiles = [];

        let html = "";

        data.files.forEach(f => {

            uploadedFiles.push(
                f.filename
            );

            html +=
                `✅ ${f.filename} (${f.total_subtitles} legendas)<br>`;
        });

        fileInfo.innerHTML = html;

        translateBtn.disabled = false;

    } catch (error) {

        console.error(error);

        fileInfo.innerHTML =
            "❌ Falha no upload";
    }
}

async function startTranslation() {

    if (uploadedFiles.length === 0) {

        alert(
            "Selecione legendas primeiro."
        );

        return;
    }

    const model =
        modelSelect.value;

    translateBtn.disabled = true;

    downloadArea.style.display = "none";

    try {

        const response =
            await fetch(
                "/api/translate",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                        "application/json"
                    },

                    body: JSON.stringify({
                        filenames:
                            uploadedFiles,
                        model:
                            model
                    })
                }
            );

        const data =
            await response.json();

        if (!data.success) {

            alert(
                data.message
            );

            translateBtn.disabled = false;

            return;
        }

    } catch (error) {

        console.error(error);

        alert(
            "Erro ao iniciar tradução."
        );

        translateBtn.disabled = false;
    }
}

async function updateProgress() {

    try {

        const response =
            await fetch(
                "/api/progress"
            );

        const data =
            await response.json();

        progressFill.style.width =
            data.progress + "%";

        progressText.innerHTML =
            data.progress + "%";

        subtitleCounter.innerHTML =
            `${data.current} / ${data.total} legendas`;

        batchInfo.innerHTML =
            `Lote ${data.current_batch} / ${data.total_batches}`;

        etaElement.innerHTML =
            `Tempo restante: ${data.eta}`;

        if (data.preview && data.preview.length > 0) {

            previewElement.innerHTML =
                data.preview.join("<br><br>");
        }

        if (data.phase === "completed" || data.phase === "idle") {

            if (data.queue_total > 0) {

                if (data.phase === "idle") {

                    queueInfo.innerHTML =
                        "✅ Todas as traduções concluídas!";

                    queueProgressFill.style.width = "100%";

                    translateBtn.disabled = false;
                }

            } else {

                translateBtn.disabled = false;

                if (data.output_file) {

                    downloadArea.style.display =
                        "block";

                    downloadLink.href =
                        `/api/download/${data.output_file}`;
                }
            }
        }

        if (data.phase === "error") {

            translateBtn.disabled = false;

            alert(
                "Erro durante a tradução."
            );
        }

        if (data.queue_total > 0) {

            queueInfo.innerHTML =
                `📁 Arquivo ${data.queue_current} / ${data.queue_total}: ${data.queue_filename}`;

            if (data.queue_total > 0) {

                const qp = Math.round(
                    ((data.queue_current - 1) / data.queue_total) * 100
                );

                queueProgressFill.style.width =
                    qp + "%";
            }
        }

    } catch (error) {

        console.error(error);
    }
}

async function updateHistory() {

    try {

        const response =
            await fetch(
                "/api/history"
            );

        const data =
            await response.json();

        if (
            !data ||
            data.length === 0
        ) {

            historyElement.innerHTML =
                "Nenhuma tradução registrada.";

            return;
        }

        let html = "";

        data.forEach(item => {

            const hasFile =
                item.output_file &&
                item.output_file.length > 0;

            html += `
                <div class="history-item">
                    <div class="history-info">
                        📄 <strong>${item.filename}</strong><br>
                        🤖 ${item.model}<br>
                        ✅ ${item.translated} legendas
                        ${item.finished_at ? `<br>🕐 ${item.finished_at}` : ""}
                    </div>
                    <div class="history-actions">
                        ${
                            hasFile
                            ? `<a href="/api/download/${item.output_file}" class="btn-download" download>Baixar</a>`
                            : ""
                        }
                    </div>
                </div>
            `;
        });

        historyElement.innerHTML =
            html;

    } catch (error) {

        console.error(error);
    }
}

async function clearHistory() {

    if (
        !confirm(
            "Tem certeza que deseja limpar todo o histórico?\n\n" +
            "Isso irá apagar todas as traduções e arquivos (uploads e traduzidos)."
        )
    ) {
        return;
    }

    try {

        const response =
            await fetch(
                "/api/clear_history",
                { method: "POST" }
            );

        const data =
            await response.json();

        if (data.success) {

            alert(
                "Histórico limpo com sucesso!"
            );

            uploadedFiles = [];

            fileInfo.innerHTML =
                "Nenhum arquivo carregado.";

            fileInput.value = "";

            updateHistory();

        } else {

            alert(
                "Erro: " + data.message
            );
        }

    } catch (error) {

        console.error(error);

        alert(
            "Erro ao limpar histórico."
        );
    }
}

fileInput.addEventListener(
    "change",
    uploadFiles
);

translateBtn.addEventListener(
    "click",
    startTranslation
);

if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener(
        "click",
        clearHistory
    );
}

updateStatus();

updateHistory();

updateProgress();

setInterval(
    updateStatus,
    10000
);

setInterval(
    updateProgress,
    1000
);

setInterval(
    updateHistory,
    10000
);
