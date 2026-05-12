// Vanilla JS — polls /api/jobs every 1.5s and renders the list.

const form = document.getElementById("dl-form");
const submitBtn = document.getElementById("submit-btn");
const errBox = document.getElementById("form-error");
const jobsEl = document.getElementById("jobs");
const countEl = document.getElementById("jobs-count");
const urlInput = document.getElementById("url");
const transcribeChk = document.getElementById("transcribe");
const languageSel = document.getElementById("language");

const TERMINAL = new Set(["done", "error", "cancelled"]);
const STATUS_PT = {
  queued: "Na fila",
  downloading: "Baixando",
  transcribing: "Transcrevendo",
  done: "Concluido",
  error: "Erro",
  cancelled: "Cancelado",
};

function showError(msg) {
  errBox.textContent = msg;
  errBox.hidden = false;
  setTimeout(() => { errBox.hidden = true; }, 6000);
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  errBox.hidden = true;

  const body = {
    url: urlInput.value.trim(),
    format: form.querySelector('input[name="format"]:checked').value,
    transcribe: transcribeChk && transcribeChk.checked,
    language: languageSel ? languageSel.value : "",
  };

  submitBtn.disabled = true;
  submitBtn.textContent = "Enviando...";

  try {
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
    urlInput.value = "";
    await refreshJobs();
  } catch (e) {
    showError(e.message || String(e));
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Adicionar a fila";
  }
});

async function refreshJobs() {
  let data;
  try {
    const resp = await fetch("/api/jobs");
    data = await resp.json();
  } catch {
    return;
  }
  renderJobs(data.jobs || []);
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobsEl.innerHTML = '<li class="empty">Nenhuma tarefa ainda.</li>';
    countEl.textContent = "";
    return;
  }

  const active = jobs.filter(j => !TERMINAL.has(j.status)).length;
  countEl.textContent = `(${jobs.length}${active ? `, ${active} ativa${active > 1 ? "s" : ""}` : ""})`;

  jobsEl.innerHTML = jobs.map(jobHtml).join("");
  jobsEl.querySelectorAll("[data-cancel]").forEach(el => {
    el.addEventListener("click", () => cancelJob(el.dataset.cancel));
  });
  jobsEl.querySelectorAll("[data-remove]").forEach(el => {
    el.addEventListener("click", () => removeJob(el.dataset.remove));
  });
}

function jobHtml(j) {
  const pct = Math.round((j.progress || 0) * 100);
  const title = escapeHtml(j.title || j.media_file || j.url);
  const status = STATUS_PT[j.status] || j.status;
  const message = escapeHtml(j.message || "");
  const isTerminal = TERMINAL.has(j.status);

  const tags = [
    `<span class="tag ${j.format}">${j.format}</span>`,
    j.transcribe ? '<span class="tag tr">tr</span>' : "",
  ].filter(Boolean).join("");

  const actions = isTerminal
    ? `<button class="danger" data-remove="${j.id}">Remover</button>`
    : `<button data-cancel="${j.id}">Cancelar</button>`;

  return `
    <li class="job ${j.status}">
      <div class="job-head">
        <div class="job-title">${title}</div>
        <div class="job-meta">${tags}<span>${status}${isTerminal ? "" : ` ${pct}%`}</span></div>
      </div>
      <div class="job-status">${message}</div>
      <div class="bar"><span style="width: ${pct}%"></span></div>
      <div class="job-actions">${actions}</div>
    </li>`;
}

async function cancelJob(id) {
  try {
    await fetch(`/api/jobs/${id}/cancel`, { method: "POST" });
  } finally {
    refreshJobs();
  }
}

async function removeJob(id) {
  try {
    await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  } finally {
    refreshJobs();
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

refreshJobs();
setInterval(refreshJobs, 1500);
