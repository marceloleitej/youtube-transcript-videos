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

// ---------- Tabs --------------------------------------------------------

const tabs = document.querySelectorAll(".tab");
const panels = {
  download: document.getElementById("tab-download"),
  library: document.getElementById("tab-library"),
};
let activeTab = "download";

tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;
    if (target === activeTab) return;
    activeTab = target;
    tabs.forEach((b) => {
      const on = b.dataset.tab === target;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    Object.entries(panels).forEach(([k, el]) => {
      const on = k === target;
      el.classList.toggle("active", on);
      el.hidden = !on;
    });
    if (target === "library") {
      refreshLibrary();
    } else {
      stopPlayback();
    }
  });
});

// ---------- Library -----------------------------------------------------

const libraryEl = document.getElementById("library");
const libraryCountEl = document.getElementById("library-count");
const platformFilterEl = document.getElementById("platform-filter");
const playerCardEl = document.getElementById("player-card");
const libraryCardEl = document.getElementById("library-card");
const playerEl = document.getElementById("player");
const playerAudioEl = document.getElementById("player-audio");
const playerTitleEl = document.getElementById("player-title");
const playerMetaEl = document.getElementById("player-meta");
const playerBackBtn = document.getElementById("player-back");

let libraryVideos = [];
let knownPlatforms = new Set();

async function refreshLibrary() {
  try {
    const resp = await fetch("/api/library");
    const data = await resp.json();
    libraryVideos = data.videos || [];
  } catch {
    libraryEl.innerHTML = '<li class="empty">Falha ao carregar a biblioteca.</li>';
    return;
  }
  syncPlatformOptions();
  renderLibrary();
}

function syncPlatformOptions() {
  const current = platformFilterEl.value;
  const platforms = new Set();
  libraryVideos.forEach((v) => {
    if (v.platform) platforms.add(v.platform);
  });
  // Only rebuild if the set changed (avoid losing focus/scroll).
  const same = platforms.size === knownPlatforms.size &&
    [...platforms].every((p) => knownPlatforms.has(p));
  if (same) return;
  knownPlatforms = platforms;
  const sorted = [...platforms].sort((a, b) => a.localeCompare(b));
  platformFilterEl.innerHTML =
    '<option value="">Todas</option>' +
    sorted.map((p) => `<option value="${escapeAttr(p)}">${escapeHtml(p)}</option>`).join("");
  if (sorted.includes(current)) platformFilterEl.value = current;
}

platformFilterEl.addEventListener("change", renderLibrary);

function renderLibrary() {
  const filter = platformFilterEl.value;
  const filtered = filter
    ? libraryVideos.filter((v) => v.platform === filter)
    : libraryVideos;

  libraryCountEl.textContent = filtered.length
    ? `(${filtered.length})`
    : "";

  if (!filtered.length) {
    libraryEl.innerHTML = `<li class="empty">${
      libraryVideos.length ? "Nenhum video com esse filtro." : "Nenhum video baixado ainda."
    }</li>`;
    return;
  }

  libraryEl.innerHTML = filtered.map(libraryItemHtml).join("");
  libraryEl.querySelectorAll("[data-play]").forEach((el) => {
    el.addEventListener("click", () => {
      const v = libraryVideos.find((x) => x.video_id === el.dataset.play);
      if (v) play(v);
    });
  });
}

function libraryItemHtml(v) {
  const title = escapeHtml(v.title || v.media_path || "(sem titulo)");
  const platform = escapeHtml(v.platform || "Outro");
  const fmt = escapeHtml(v.format || "");
  const dur = formatDuration(v.duration_seconds);
  return `
    <li class="library-item" data-play="${escapeAttr(v.video_id)}">
      <div class="library-thumb">
        <span class="library-fmt ${fmt}">${fmt.toUpperCase() || "?"}</span>
      </div>
      <div class="library-body">
        <div class="library-title">${title}</div>
        <div class="library-meta">
          <span class="pill">${platform}</span>
          ${dur ? `<span>${dur}</span>` : ""}
        </div>
      </div>
    </li>`;
}

function play(v) {
  const isAudio = (v.format || "").toLowerCase() === "mp3";
  stopPlayback();
  playerTitleEl.textContent = v.title || v.media_path;
  playerMetaEl.textContent = [
    v.platform || "",
    formatDuration(v.duration_seconds),
  ].filter(Boolean).join(" · ");

  if (isAudio) {
    playerEl.hidden = true;
    playerAudioEl.hidden = false;
    playerAudioEl.src = v.media_url;
    playerAudioEl.play().catch(() => {});
  } else {
    playerAudioEl.hidden = true;
    playerEl.hidden = false;
    playerEl.src = v.media_url;
    playerEl.play().catch(() => {});
  }
  playerCardEl.hidden = false;
  libraryCardEl.hidden = true;
  playerCardEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

function stopPlayback() {
  try { playerEl.pause(); } catch {}
  try { playerAudioEl.pause(); } catch {}
  playerEl.removeAttribute("src");
  playerAudioEl.removeAttribute("src");
  playerEl.load && playerEl.load();
  playerAudioEl.load && playerAudioEl.load();
}

playerBackBtn.addEventListener("click", () => {
  stopPlayback();
  playerCardEl.hidden = true;
  libraryCardEl.hidden = false;
});

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  if (!s) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function escapeAttr(s) {
  return escapeHtml(s);
}
