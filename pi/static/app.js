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
  jobsEl.querySelectorAll("[data-retry]").forEach(el => {
    el.addEventListener("click", () => retryJob(el.dataset.retry, el));
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
    ? `<button data-retry="${j.id}">Tentar de novo</button>
       <button class="danger" data-remove="${j.id}">Remover</button>`
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

async function retryJob(id, btn) {
  if (btn) btn.disabled = true;
  try {
    const resp = await fetch(`/api/jobs/${id}/retry`, { method: "POST" });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
  } catch (e) {
    showError("Retry falhou: " + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
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
const searchEl = document.getElementById("library-search");
const playerCardEl = document.getElementById("player-card");
const libraryCardEl = document.getElementById("library-card");
const playerEl = document.getElementById("player");
const playerAudioEl = document.getElementById("player-audio");
const playerTitleEl = document.getElementById("player-title");
const playerMetaEl = document.getElementById("player-meta");
const playerBackBtn = document.getElementById("player-back");

const NO_FOLDER = "__nofolder__";
const COLLAPSE_KEY = "videos-pi.collapse.v1";

let libraryVideos = [];
let knownPlatforms = new Set();
let collapsedFolders = loadCollapseState();

// Platform badge labels & colors mirror the PC app (ui/history_panel.py).
const PLATFORM_BADGES = {
  youtube:   { label: "YT", color: "#FF0000" },
  tiktok:    { label: "TT", color: "#00f2ea" },
  instagram: { label: "IG", color: "#E1306C" },
  facebook:  { label: "FB", color: "#1877F2" },
};

function badgeFor(platform) {
  return PLATFORM_BADGES[(platform || "").toLowerCase()] || { label: "??", color: "#666" };
}

// ----- Folder hierarchy helpers (mirror core path logic) -----

function folderParts(folder) {
  if (!folder) return [];
  return folder.split("/").map((p) => p.trim()).filter(Boolean);
}

function folderDepth(folder) {
  return folderParts(folder).length;
}

function folderLeaf(folder) {
  const parts = folderParts(folder);
  return parts.length ? parts[parts.length - 1] : "";
}

function folderBelongsTo(folder, ancestor) {
  if (!ancestor) return true;
  return folder === ancestor || folder.startsWith(ancestor + "/");
}

function expandAncestors(folders) {
  const seen = new Set();
  folders.forEach((f) => {
    const parts = folderParts(f);
    for (let i = 1; i <= parts.length; i++) {
      seen.add(parts.slice(0, i).join("/"));
    }
  });
  return [...seen];
}

function anyAncestorCollapsed(folder) {
  const parts = folderParts(folder);
  for (let i = 1; i < parts.length; i++) {
    const ancestor = parts.slice(0, i).join("/");
    if (collapsedFolders[ancestor]) return true;
  }
  return false;
}

function loadCollapseState() {
  try {
    const raw = localStorage.getItem(COLLAPSE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveCollapseState() {
  try {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify(collapsedFolders));
  } catch {}
}

// ----- Library data load -----

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
if (searchEl) {
  searchEl.addEventListener("input", renderLibrary);
}

// ----- Rendering -----

function filteredVideos() {
  const plat = platformFilterEl.value;
  const search = (searchEl ? searchEl.value : "").trim().toLowerCase();
  return libraryVideos.filter((v) => {
    if (plat && v.platform !== plat) return false;
    if (search && !(v.title || "").toLowerCase().includes(search)) return false;
    return true;
  });
}

function renderLibrary() {
  const filtered = filteredVideos();
  libraryCountEl.textContent = filtered.length ? `(${filtered.length})` : "";

  if (!filtered.length) {
    libraryEl.innerHTML = `<li class="empty">${
      libraryVideos.length ? "Nenhum video com esse filtro." : "Nenhum video baixado ainda."
    }</li>`;
    return;
  }

  const search = (searchEl ? searchEl.value : "").trim();
  // While searching: flat list (easier to scan across folders).
  if (search) {
    libraryEl.innerHTML = filtered.map(libraryItemHtml).join("");
    bindLibraryItems();
    return;
  }

  // Group by folder + render hierarchical headers.
  const groups = {};
  filtered.forEach((v) => {
    const k = v.folder || "";
    (groups[k] = groups[k] || []).push(v);
  });

  const withItems = Object.keys(groups).filter((f) => f);
  const allFolders = new Set([...withItems, ...expandAncestors(withItems)]);
  const sortedFolders = [...allFolders].sort((a, b) => {
    const ap = folderParts(a), bp = folderParts(b);
    const n = Math.min(ap.length, bp.length);
    for (let i = 0; i < n; i++) {
      const c = ap[i].localeCompare(bp[i], "pt", { sensitivity: "base" });
      if (c !== 0) return c;
    }
    return ap.length - bp.length;
  });

  const html = [];

  // "Sem pasta" group goes last only if it has items.
  for (const folder of sortedFolders) {
    const items = groups[folder] || [];
    let descendantCount = items.length;
    for (const k of Object.keys(groups)) {
      if (k && k !== folder && k.startsWith(folder + "/")) {
        descendantCount += groups[k].length;
      }
    }
    html.push(folderHeaderHtml(folder, descendantCount));
    // Inline items appear directly after their header.
    for (const v of items) html.push(libraryItemHtml(v, folder));
  }

  if (groups[""]) {
    html.push(folderHeaderHtml("", groups[""].length));
    for (const v of groups[""]) html.push(libraryItemHtml(v, ""));
  }

  libraryEl.innerHTML = html.join("");
  applyCollapseVisibility();
  bindFolderHeaders();
  bindLibraryItems();
}

function folderHeaderHtml(folder, count) {
  const depth = folderDepth(folder);
  const collapsed = !!collapsedFolders[folder || NO_FOLDER];
  const label = folder ? folderLeaf(folder) : "Sem pasta";
  const arrow = collapsed ? "&#9654;" : "&#9660;";
  return `
    <li class="folder-header${collapsed ? " collapsed" : ""}"
        data-folder="${escapeAttr(folder)}"
        data-depth="${depth}"
        style="--depth: ${depth};">
      <span class="folder-arrow">${arrow}</span>
      <span class="folder-name">${escapeHtml(label)}</span>
      <span class="folder-count">${count}</span>
    </li>`;
}

function libraryItemHtml(v, folder = "") {
  const title = escapeHtml(v.title || v.media_path || "(sem titulo)");
  const fmt = (v.format || "").toLowerCase();
  const dur = formatDuration(v.duration_seconds);
  const date = formatDate(v.created_at);
  const hasTr = !!v.has_transcription;
  const badge = badgeFor(v.platform);
  const thumbStyle = v.thumb_url
    ? `background-image: url('${escapeAttr(v.thumb_url)}');`
    : "";
  const filename = (v.media_path || "").split(/[\\/]/).pop();

  const meta = [
    date ? `<span>${escapeHtml(date)}</span>` : "",
    dur ? `<span>${escapeHtml(dur)}</span>` : "",
    `<span class="${hasTr ? "tr-ok" : "tr-no"}">${hasTr ? "&#10003; Transcrito" : "&#9675; Sem transcricao"}</span>`,
  ].filter(Boolean).join('<span class="dot-sep">&middot;</span>');

  const depth = folderDepth(folder);
  return `
    <li class="library-item"
        data-play="${escapeAttr(v.video_id)}"
        data-folder="${escapeAttr(folder)}"
        style="--depth: ${depth};">
      <div class="library-thumb" style="${thumbStyle}">
        <span class="library-badge" style="background:${badge.color};">${badge.label}</span>
        ${!thumbStyle ? `<span class="library-fmt ${fmt}">${(fmt || "?").toUpperCase()}</span>` : ""}
      </div>
      <div class="library-body">
        <div class="library-title">
          ${title}
          <span class="fmt-pill ${fmt}">${(fmt || "").toUpperCase()}</span>
        </div>
        <div class="library-meta">${meta}</div>
      </div>
      <button type="button" class="library-delete"
              data-delete="${escapeAttr(filename)}"
              aria-label="Excluir" title="Excluir">&times;</button>
    </li>`;
}

function bindLibraryItems() {
  libraryEl.querySelectorAll("[data-play]").forEach((el) => {
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-delete]")) return;
      const v = libraryVideos.find((x) => x.video_id === el.dataset.play);
      if (v) play(v);
    });
  });
  libraryEl.querySelectorAll("[data-delete]").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.stopPropagation();
      deleteLibraryItem(el);
    });
  });
}

async function deleteLibraryItem(btn) {
  const filename = btn.dataset.delete;
  if (!filename) return;
  const v = libraryVideos.find(
    (x) => (x.media_path || "").split(/[\\/]/).pop() === filename,
  );
  const title = (v && v.title) || filename;
  const ok = window.confirm(
    `Excluir "${title}"?\n\nRemove o arquivo + sidecar JSON. O Syncthing propaga a remocao pro PC.`,
  );
  if (!ok) return;
  btn.disabled = true;
  try {
    const resp = await fetch(`/api/library/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
    await refreshLibrary();
  } catch (e) {
    btn.disabled = false;
    window.alert("Falha ao excluir: " + (e.message || e));
  }
}

function bindFolderHeaders() {
  libraryEl.querySelectorAll(".folder-header").forEach((el) => {
    el.addEventListener("click", () => {
      const folder = el.dataset.folder || "";
      const key = folder || NO_FOLDER;
      const nowCollapsed = !collapsedFolders[key];
      if (nowCollapsed) collapsedFolders[key] = true;
      else delete collapsedFolders[key];
      saveCollapseState();
      applyCollapseVisibility();
    });
  });
}

function applyCollapseVisibility() {
  const headers = libraryEl.querySelectorAll(".folder-header");
  const items = libraryEl.querySelectorAll(".library-item");

  headers.forEach((el) => {
    const folder = el.dataset.folder || "";
    const key = folder || NO_FOLDER;
    const collapsed = !!collapsedFolders[key];
    el.classList.toggle("collapsed", collapsed);
    el.querySelector(".folder-arrow").innerHTML = collapsed ? "&#9654;" : "&#9660;";
    // Hide the header itself when any ancestor is collapsed.
    const hidden = folder ? anyAncestorCollapsed(folder) : false;
    el.style.display = hidden ? "none" : "";
  });

  items.forEach((el) => {
    const folder = el.dataset.folder || "";
    const key = folder || NO_FOLDER;
    const ownCollapsed = !!collapsedFolders[key];
    const ancestorCollapsed = folder ? anyAncestorCollapsed(folder) : false;
    el.style.display = (ownCollapsed || ancestorCollapsed) ? "none" : "";
  });
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
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
