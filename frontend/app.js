/* ============================================================================
   Brand-Locked Image Generator — frontend controller
   ==========================================================================*/
"use strict";

// ---- Client-side slot definitions (mirror backend order/labels) ----------
const SLOTS = [
  { slot: "01_Hero", label: "Hero Shot", variant: "hero", field: "hero" },
  { slot: "02_Process", label: "Process Poster", variant: "process", field: "process" },
  { slot: "03_Lifestyle", label: "Lifestyle Poster", variant: "lifestyle", field: "lifestyle" },
  { slot: "04_FlatLay", label: "Flat Lay", variant: "flatlay", field: "flatlay" },
];
const SLOT_BY_KEY = Object.fromEntries(SLOTS.map((s) => [s.slot, s]));

// ---- State ----------------------------------------------------------------
const state = {
  providers: [],
  keys: {},
  activeProvider: "huggingface",
  connStatus: {},
  logoBase64: null,
  logoDataUrl: null,
  brandName: "Gau Bhoomi Naturals",
  mode: "auto",
  autoPrompts: null,      // { slot: {prompt, negative, variant} } after preview
  autoPromptsSource: null, // "curated" | "generic" — where the preview came from
  batchRows: [],
  dryRun: false,
  generating: false,
  abort: null,
  results: {},            // index -> { product, size, category, job, cells }
  order: [],              // ordered indices for the current run
  genContext: null,       // params needed to retry a slot
  progress: null,         // { total, done }
};

// ---- Tiny helpers ---------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  (Array.isArray(children) ? children : [children]).forEach((c) => {
    if (c == null) return;
    n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return n;
}
function slugify(s) {
  return (s || "").replace(/[^\w\s-]/g, "").trim().replace(/[\s-]+/g, "_") || "item";
}
function b64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function toast(msg, kind = "") {
  const t = el("div", { class: `toast ${kind}`, text: msg });
  $("#toast-wrap").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

// ---- Init -----------------------------------------------------------------
document.addEventListener("DOMContentLoaded", init);

async function init() {
  restoreSession();
  wireHeader();
  wireCollapsibles();
  wireLogo();
  wireModeTabs();
  wireAutoMode();
  wireCustomMode();
  wireBatchMode();
  wireGenerate();
  wireModal();
  await loadProviders();
  refreshGenerateButton();
}

// ---- Session persistence (keys + brand only; never logos/images) ----------
function restoreSession() {
  try {
    const raw = sessionStorage.getItem("blig_keys");
    if (raw) state.keys = JSON.parse(raw) || {};
    const ap = sessionStorage.getItem("blig_active");
    if (ap) state.activeProvider = ap;
    const bn = sessionStorage.getItem("blig_brand");
    if (bn) { state.brandName = bn; }
  } catch (e) { /* ignore corrupt storage */ }
}
function saveKeys() {
  try { sessionStorage.setItem("blig_keys", JSON.stringify(state.keys)); } catch (e) {}
}

// ---- Header ---------------------------------------------------------------
function wireHeader() {
  const dry = $("#dry-run-toggle");
  dry.addEventListener("change", () => {
    state.dryRun = dry.checked;
    refreshGenerateButton();
  });
  const brand = $("#brand-name");
  brand.value = state.brandName;
  brand.addEventListener("input", () => {
    state.brandName = brand.value.trim() || "Gau Bhoomi Naturals";
    try { sessionStorage.setItem("blig_brand", state.brandName); } catch (e) {}
  });
}

function wireCollapsibles() {
  $$(".card-head[data-toggle]").forEach((h) => {
    h.addEventListener("click", () => h.parentElement.classList.toggle("collapsed"));
  });
}

// ---- Providers / API keys -------------------------------------------------
async function loadProviders() {
  try {
    const r = await fetch("/api/providers");
    const data = await r.json();
    state.providers = data.providers || [];
  } catch (e) {
    toast("Could not load providers from server.", "bad");
    return;
  }
  if (!state.providers.some((p) => p.id === state.activeProvider)) {
    state.activeProvider = state.providers[0]?.id || "huggingface";
  }
  renderProviders();
  updateActiveProviderLabel();
}

function renderProviders() {
  const list = $("#provider-list");
  list.innerHTML = "";
  state.providers.forEach((p) => {
    const active = p.id === state.activeProvider;
    const status = state.connStatus[p.id];
    const row = el("div", { class: `provider-row${active ? " active" : ""}`, id: `prow-${p.id}` });

    const radio = el("input", { type: "radio", name: "active-provider", ...(active ? { checked: "checked" } : {}) });
    radio.addEventListener("change", () => {
      state.activeProvider = p.id;
      try { sessionStorage.setItem("blig_active", p.id); } catch (e) {}
      renderProviders();
      updateActiveProviderLabel();
      refreshGenerateButton();
    });

    const top = el("div", { class: "prow-top" }, [
      radio,
      el("div", {}, [
        el("div", { class: "pname", text: p.label }),
        el("div", { class: "pquality", text: p.quality }),
      ]),
      p.free_tier ? el("span", { class: "free-tag", text: "free tier" }) : null,
    ]);

    const dot = el("span", { class: `status-dot ${status || ""}`, id: `dot-${p.id}` });
    const keyInput = el("input", {
      class: "input", type: "password", placeholder: "Paste API key",
      value: state.keys[p.id] || "",
    });
    keyInput.addEventListener("input", () => {
      state.keys[p.id] = keyInput.value.trim();
      saveKeys();
      state.connStatus[p.id] = null;
      $(`#dot-${p.id}`).className = "status-dot";
      $(`#kmsg-${p.id}`).textContent = "";
      refreshGenerateButton();
    });
    const testBtn = el("button", { class: "btn btn-sm", text: "Test" });
    testBtn.addEventListener("click", () => testConnection(p.id));

    const keyLine = el("div", { class: "key-line" }, [dot, keyInput, testBtn]);
    const msg = el("div", { class: "key-msg", id: `kmsg-${p.id}` });
    const help = el("div", { class: "key-help", text: p.key_help });

    row.appendChild(top);
    row.appendChild(keyLine);
    row.appendChild(msg);
    row.appendChild(help);
    list.appendChild(row);
  });
}

function updateActiveProviderLabel() {
  const p = state.providers.find((x) => x.id === state.activeProvider);
  $("#active-provider-label").textContent = p ? p.label : state.activeProvider;
}

async function testConnection(providerId) {
  const key = (state.keys[providerId] || "").trim();
  const dot = $(`#dot-${providerId}`);
  const msg = $(`#kmsg-${providerId}`);
  if (!key) { msg.className = "key-msg bad"; msg.textContent = "Enter a key first."; return; }
  dot.className = "status-dot testing";
  msg.className = "key-msg"; msg.textContent = "Testing…";
  state.connStatus[providerId] = "testing";
  try {
    const r = await fetch("/api/test-connection", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerId, api_key: key }),
    });
    const data = await r.json();
    if (data.ok) {
      dot.className = "status-dot ok"; msg.className = "key-msg ok";
      state.connStatus[providerId] = "ok";
    } else {
      dot.className = "status-dot bad"; msg.className = "key-msg bad";
      state.connStatus[providerId] = "bad";
    }
    msg.textContent = data.message || (data.ok ? "Connected" : "Failed");
  } catch (e) {
    dot.className = "status-dot bad"; msg.className = "key-msg bad";
    msg.textContent = "Network error during test.";
    state.connStatus[providerId] = "bad";
  }
}

// ---- Logo -----------------------------------------------------------------
function wireLogo() {
  const dz = $("#logo-dropzone");
  const file = $("#logo-file");
  dz.addEventListener("click", () => file.click());
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault(); dz.classList.remove("drag");
    if (e.dataTransfer.files[0]) handleLogoFile(e.dataTransfer.files[0]);
  });
  file.addEventListener("change", () => { if (file.files[0]) handleLogoFile(file.files[0]); });
  $("#logo-clear").addEventListener("click", clearLogo);
}

function handleLogoFile(f) {
  if (!f.type.startsWith("image/")) { toast("Please upload an image file (PNG recommended).", "bad"); return; }
  if (f.size > 8 * 1024 * 1024) { toast("Logo is over 8 MB — please use a smaller PNG.", "bad"); return; }
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = reader.result;
    state.logoDataUrl = dataUrl;
    state.logoBase64 = String(dataUrl).split(",")[1] || null;
    $("#logo-thumb").src = dataUrl;
    $("#logo-name").textContent = `${f.name} · ${(f.size / 1024).toFixed(0)} KB`;
    $("#logo-dropzone").style.display = "none";
    $("#logo-preview").style.display = "flex";
    refreshGenerateButton();
  };
  reader.onerror = () => toast("Could not read that file.", "bad");
  reader.readAsDataURL(f);
}

function clearLogo() {
  state.logoBase64 = null; state.logoDataUrl = null;
  $("#logo-file").value = "";
  $("#logo-dropzone").style.display = "block";
  $("#logo-preview").style.display = "none";
  refreshGenerateButton();
}

// ---- Mode tabs ------------------------------------------------------------
function wireModeTabs() {
  $$("#mode-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$("#mode-tabs .tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      state.mode = tab.dataset.mode;
      $$(".tab-pane").forEach((p) => p.classList.toggle("active", p.dataset.pane === state.mode));
      refreshGenerateButton();
    });
  });
}

// ---- Auto mode ------------------------------------------------------------
function wireAutoMode() {
  ["a-product", "a-size", "a-category"].forEach((id) => {
    $(`#${id}`).addEventListener("input", () => { state.autoPrompts = null; state.autoPromptsSource = null; $("#a-prompt-cards").innerHTML = ""; refreshGenerateButton(); });
  });
  $("#a-preview").addEventListener("click", previewAutoPrompts);
}

async function previewAutoPrompts() {
  const product = $("#a-product").value.trim();
  if (!product) { toast("Enter a product name first.", "bad"); return; }
  const btn = $("#a-preview");
  btn.disabled = true; btn.textContent = "Generating prompts…";
  try {
    const r = await fetch("/api/preview-prompts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_name: product, size: $("#a-size").value.trim(),
        category: $("#a-category").value, brand_name: state.brandName,
      }),
    });
    const data = await r.json();
    if (!data.ok) {
      renderProfileError(data);
      state.autoPrompts = null;
      state.autoPromptsSource = null;
    } else {
      state.autoPrompts = data.prompts;
      state.autoPromptsSource = data.source;
      renderPromptCards(data.prompts, data.source);
    }
  } catch (e) {
    toast("Could not reach the server for prompt preview.", "bad");
  } finally {
    btn.disabled = false; btn.textContent = "Preview the 4 prompts →";
    refreshGenerateButton();
  }
}

function renderProfileError(data) {
  // The only remaining failure case is a blank product name — the universal
  // fallback engine means every non-blank product name now succeeds here.
  const wrap = $("#a-prompt-cards");
  wrap.innerHTML = "";
  wrap.appendChild(el("div", { class: "audit-issues", style: "list-style:none;padding-left:0;margin:0;" }, [
    el("div", { text: data.error || "Could not generate prompts." }),
  ]));
}

function renderPromptCards(prompts, source) {
  const wrap = $("#a-prompt-cards");
  wrap.innerHTML = "";
  if (source === "generic") {
    wrap.appendChild(el("div", {
      class: "key-help", style: "margin-bottom:10px;color:var(--text-dim);",
      text: "ℹ No hand-tuned profile for this product — using the smart generic template engine instead. Still on-brand and unique; edit any prompt below, or switch to Custom Prompts for full control.",
    }));
  }
  SLOTS.forEach((s) => {
    const spec = prompts[s.slot];
    if (!spec) return;
    const ta = el("textarea", { spellcheck: "false" });
    ta.value = spec.prompt;
    ta.addEventListener("input", () => { state.autoPrompts[s.slot].prompt = ta.value; });
    const card = el("div", { class: "prompt-card" }, [
      el("div", { class: "pc-head" }, [
        el("span", { class: "pc-title", text: s.label }),
        el("span", { class: "pquality", text: s.variant === "hero" ? "no logo" : "logo composited" }),
      ]),
      ta,
    ]);
    wrap.appendChild(card);
  });
}

// ---- Custom mode ----------------------------------------------------------
function wireCustomMode() {
  ["c-hero", "c-process", "c-lifestyle", "c-flatlay"].forEach((id) => {
    $(`#${id}`).addEventListener("input", refreshGenerateButton);
  });
  $("#c-neg-toggle").addEventListener("change", (e) => {
    $("#c-neg-wrap").style.display = e.target.checked ? "block" : "none";
  });
}

// ---- Batch mode -----------------------------------------------------------
function wireBatchMode() {
  const dz = $("#csv-dropzone");
  const file = $("#csv-file");
  dz.addEventListener("click", () => file.click());
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault(); dz.classList.remove("drag");
    if (e.dataTransfer.files[0]) readCsv(e.dataTransfer.files[0]);
  });
  file.addEventListener("change", () => { if (file.files[0]) readCsv(file.files[0]); });
}

function readCsv(f) {
  const reader = new FileReader();
  reader.onload = () => { parseCsv(String(reader.result)); };
  reader.onerror = () => toast("Could not read the CSV.", "bad");
  reader.readAsText(f);
}

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (!lines.length) { toast("CSV is empty.", "bad"); return; }
  const header = splitCsvLine(lines[0]).map((h) => h.trim().toLowerCase());
  const iName = header.indexOf("product_name");
  const iSize = header.indexOf("size");
  const iCat = header.indexOf("category");
  const rows = [];
  const startRow = iName === -1 ? 0 : 1;   // tolerate a headerless file
  const nameCol = iName === -1 ? 0 : iName;
  const sizeCol = iSize === -1 ? 1 : iSize;
  const catCol = iCat === -1 ? 2 : iCat;
  for (let i = startRow; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]);
    const name = (cells[nameCol] || "").trim();
    if (!name) continue;
    rows.push({
      product_name: name,
      size: (cells[sizeCol] || "").trim(),
      category: (cells[catCol] || "").trim() || "Uncategorised",
    });
  }
  if (!rows.length) { toast("No product rows found in that CSV.", "bad"); return; }
  state.batchRows = rows;
  renderBatchTable();
  refreshGenerateButton();
}

function splitCsvLine(line) {
  // Handles simple quoted fields with commas inside quotes.
  const out = [];
  let cur = "", inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === "," && !inQ) { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}

function renderBatchTable() {
  const wrap = $("#batch-table-wrap");
  const table = $("#batch-table");
  table.innerHTML = "";
  table.appendChild(el("tr", {}, [
    el("th", { text: "#" }), el("th", { text: "Product" }),
    el("th", { text: "Size" }), el("th", { text: "Category" }),
  ]));
  state.batchRows.forEach((r, i) => {
    table.appendChild(el("tr", {}, [
      el("td", { text: String(i + 1) }),
      el("td", { text: r.product_name }),
      el("td", { text: r.size || "—" }),
      el("td", { text: r.category }),
    ]));
  });
  wrap.style.display = "block";
  $("#batch-count").textContent =
    `${state.batchRows.length} products × 4 images = ${state.batchRows.length * 4} total`;
}

// ---- Generate button state ------------------------------------------------
function refreshGenerateButton() {
  const btn = $("#generate-btn");
  const hint = $("#gen-hint");
  if (state.generating) { btn.disabled = true; btn.textContent = "Generating…"; hint.textContent = ""; return; }
  btn.textContent = state.dryRun ? "Generate (Dry Run)" : "Generate";

  const problems = [];
  if (!state.logoBase64) problems.push("lock a brand logo");
  if (!state.dryRun) {
    const key = (state.keys[state.activeProvider] || "").trim();
    if (!key) problems.push("add the active provider's API key");
  }
  if (state.mode === "auto" && !$("#a-product").value.trim()) problems.push("enter a product name");
  if (state.mode === "custom") {
    const missing = SLOTS.some((s) => !$(`#c-${s.field}`).value.trim());
    if (missing) problems.push("fill in all four custom prompts");
  }
  if (state.mode === "batch" && !state.batchRows.length) problems.push("upload a products CSV");

  btn.disabled = problems.length > 0;
  hint.textContent = problems.length ? "To generate: " + problems.join(", ") + "." : "";
}

// ---- Generate flow --------------------------------------------------------
function wireGenerate() {
  $("#generate-btn").addEventListener("click", startGeneration);
  $("#clear-results").addEventListener("click", clearResults);
  $("#dl-batch").addEventListener("click", downloadBatchZip);
}

function clearResults() {
  state.results = {}; state.order = [];
  $("#results-area").innerHTML = "";
  $("#results-area").appendChild(buildEmptyState());
  $("#results-actions").style.display = "none";
  $("#audit-area").innerHTML = "";
  $("#progress-area").innerHTML = "";
}

function buildEmptyState() {
  return el("div", { class: "empty-state" }, [
    el("div", { class: "big", text: "🖼️" }),
    el("h3", { text: "No images yet" }),
    el("p", { html: "Add an API key (or flip on <strong>Dry Run</strong>), lock a brand logo, describe a product, and hit <strong>Generate</strong>." }),
  ]);
}

function buildRequestBody() {
  const base = {
    provider: state.activeProvider,
    api_key: state.keys[state.activeProvider] || "",
    logo_base64: state.logoBase64,
    brand_name: state.brandName,
    dry_run: state.dryRun,
  };
  if (state.mode === "batch") {
    return { url: "/api/generate-batch", body: { ...base, products: state.batchRows } };
  }
  const single = {
    ...base,
    product_name: state.mode === "auto" ? $("#a-product").value.trim() : "Custom",
    size: state.mode === "auto" ? $("#a-size").value.trim() : "",
    category: state.mode === "auto" ? $("#a-category").value : "Other",
  };
  if (state.mode === "custom") {
    single.custom_prompts = {
      hero: $("#c-hero").value.trim(), process: $("#c-process").value.trim(),
      lifestyle: $("#c-lifestyle").value.trim(), flatlay: $("#c-flatlay").value.trim(),
    };
    const neg = $("#c-negative").value.trim();
    if (neg) single.custom_negatives = Object.fromEntries(SLOTS.map((s) => [s.field, neg]));
  } else if (state.autoPrompts) {
    // user previewed (and maybe edited) — send verbatim so edits are honored
    single.raw_prompts = Object.fromEntries(
      SLOTS.map((s) => [s.slot, state.autoPrompts[s.slot]?.prompt || ""]));
    single.custom_negatives = Object.fromEntries(
      SLOTS.map((s) => [s.slot, state.autoPrompts[s.slot]?.negative || ""]));
  }
  return { url: "/api/generate", body: single };
}

async function startGeneration() {
  const { url, body } = buildRequestBody();
  // Reset run state.
  state.results = {}; state.order = [];
  state.genContext = {
    provider: body.provider, api_key: body.api_key, logo_base64: body.logo_base64,
    brand_name: body.brand_name, dry_run: body.dry_run,
    mode: state.mode, custom_prompts: body.custom_prompts || null,
    custom_negatives: body.custom_negatives || null, raw_prompts: body.raw_prompts || null,
    jobs: state.mode === "batch" ? state.batchRows.slice()
      : [{ product_name: body.product_name, size: body.size, category: body.category }],
  };
  state.generating = true;
  refreshGenerateButton();
  $("#results-area").innerHTML = "";
  $("#results-actions").style.display = "none";
  $("#audit-area").innerHTML = "";
  renderProgressPanel();

  state.abort = new AbortController();
  try {
    await streamEvents(url, body, state.abort.signal, (ev) => handleEvent(ev, false));
  } catch (e) {
    if (e.name !== "AbortError") { toast("Generation stream error: " + e.message, "bad"); logLine("stream error: " + e.message, "err"); }
  }
  finishGeneration();
}

function cancelGeneration() {
  if (state.abort) state.abort.abort();
  logLine("Cancelled by user — finishing after current image.", "warn");
}

function finishGeneration() {
  state.generating = false;
  state.abort = null;
  refreshGenerateButton();
  const p = $("#progress-panel-inner");
  if (p) { const c = $("#pp-cancel"); if (c) { c.textContent = "Done"; c.disabled = true; } }
  if (state.order.length) $("#results-actions").style.display = "flex";
}

// ---- SSE stream reader ----------------------------------------------------
async function streamEvents(url, body, signal, onEvent) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), signal,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { const j = await resp.json(); detail = JSON.stringify(j).slice(0, 200); } catch (e) {}
    throw new Error(detail);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      let ev;
      try { ev = JSON.parse(dataLine.slice(5).trim()); } catch (e) { continue; }
      onEvent(ev);
    }
  }
}

// ---- Event handling -------------------------------------------------------
function handleEvent(ev, isRetry) {
  switch (ev.type) {
    case "audit": renderAudit(ev); break;
    case "batch_start":
      if (!isRetry) { state.progress = { total: ev.total_images, done: 0 }; updateProgressBars(); }
      break;
    case "product_start":
      if (!isRetry) ensureProductBlock(ev);
      setProgressProduct(ev.product, ev.index);
      break;
    case "prompts": storePrompts(ev); break;
    case "progress": onProgress(ev, isRetry); break;
    case "image": onImage(ev, isRetry); break;
    case "error": onSlotError(ev, isRetry); break;
    case "product_complete": logLine(`✔ ${ev.product}: ${ev.ok}/${ev.total} images`, ev.ok === ev.total ? "ok" : "warn"); break;
    case "complete": logLine(`Batch complete — ${ev.total_ok}/${ev.total} images.`, "ok"); break;
    case "fatal": onFatal(ev); break;
    default: break;
  }
}

function onFatal(ev) {
  logLine("FATAL: " + ev.message, "err");
  toast(ev.message, "bad");
  // Never leave cells spinning: turn any still-loading cell into an error card.
  state.order.forEach((index) => {
    const res = state.results[index];
    if (!res) return;
    Object.entries(res.cells).forEach(([slot, cell]) => {
      if (cell.status === "loading") {
        cell.status = "error";
        cell.error = ev.message;
        renderCell(index, slot);
      }
    });
  });
}

function storePrompts(ev) {
  const res = state.results[ev.index];
  if (!res) return;
  Object.entries(ev.prompts).forEach(([slot, spec]) => {
    if (res.cells[slot]) { res.cells[slot].prompt = spec.prompt; res.cells[slot].negative = spec.negative; }
  });
  if (ev.source === "generic") {
    const badge = $(`#pb-source-${ev.index}`);
    if (badge) { badge.textContent = "smart generic template"; badge.style.display = "inline"; }
  }
}

function onProgress(ev, isRetry) {
  const cell = getCell(ev.index, ev.slot);
  if (cell) setCellLoading(ev.index, ev.slot, ev.message);
  logLine(`[${ev.index + 1}·${SLOT_BY_KEY[ev.slot]?.label || ev.slot}] ${ev.message}`, "dim");
  setProgressImage(ev.label);
}

function onImage(ev, isRetry) {
  const res = state.results[ev.index];
  if (!res) return;
  res.cells[ev.slot] = { ...(res.cells[ev.slot] || {}), status: "ok", data: ev.data, label: ev.label, variant: ev.variant };
  renderCell(ev.index, ev.slot);
  logLine(`✔ ${res.product} — ${ev.label} ready`, "ok");
  if (!isRetry && state.progress) { state.progress.done++; updateProgressBars(); }
  updateProductActions(ev.index);
}

function onSlotError(ev, isRetry) {
  const res = state.results[ev.index];
  if (!res) return;
  res.cells[ev.slot] = { ...(res.cells[ev.slot] || {}), status: "error", error: ev.message, label: ev.label };
  renderCell(ev.index, ev.slot);
  logLine(`✖ ${res.product} — ${ev.label}: ${ev.message}`, "err");
  if (!isRetry && state.progress) { state.progress.done++; updateProgressBars(); }
}

// ---- Progress panel -------------------------------------------------------
function renderProgressPanel() {
  const area = $("#progress-area");
  area.innerHTML = "";
  const panel = el("div", { class: "progress-panel", id: "progress-panel-inner" }, [
    el("div", { class: "pp-top" }, [
      el("div", {}, [
        el("div", { class: "pp-title", id: "pp-product", text: "Preparing…" }),
        el("div", { class: "pp-sub", id: "pp-image", text: "" }),
      ]),
      el("button", { class: "btn btn-sm btn-danger", id: "pp-cancel", text: "Cancel", onclick: cancelGeneration }),
    ]),
    el("div", { class: "bar-label" }, [el("span", { text: "Overall progress" }), el("span", { id: "pp-count", text: "0 / 0" })]),
    el("div", { class: "bar" }, [el("span", { id: "pp-bar" })]),
    el("div", { class: "log-toggle", id: "log-toggle" }, ["▸ Live log"]),
    el("div", { class: "log-stream", id: "log-stream" }),
  ]);
  area.appendChild(panel);
  $("#log-toggle").addEventListener("click", () => {
    const s = $("#log-stream"); const open = s.classList.toggle("open");
    $("#log-toggle").firstChild.textContent = (open ? "▾" : "▸") + " Live log";
  });
}

function setProgressProduct(name, index) {
  const e = $("#pp-product"); if (e) e.textContent = `Product ${index + 1}: ${name}`;
}
function setProgressImage(label) { const e = $("#pp-image"); if (e) e.textContent = "Working on: " + label; }
function updateProgressBars() {
  if (!state.progress) return;
  const { done, total } = state.progress;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const bar = $("#pp-bar"); if (bar) bar.style.width = pct + "%";
  const cnt = $("#pp-count"); if (cnt) cnt.textContent = `${done} / ${total}`;
}
function logLine(text, cls) {
  const s = $("#log-stream"); if (!s) return;
  const time = new Date().toLocaleTimeString();
  s.appendChild(el("div", { class: cls ? `l-${cls}` : "", text: `${time}  ${text}` }));
  s.scrollTop = s.scrollHeight;
}

// ---- Results gallery ------------------------------------------------------
function ensureProductBlock(ev) {
  if (state.results[ev.index]) return;
  state.results[ev.index] = {
    product: ev.product, size: ev.size, category: ev.category,
    job: { product_name: ev.product, size: ev.size, category: ev.category },
    cells: {},
  };
  state.order.push(ev.index);
  SLOTS.forEach((s) => { state.results[ev.index].cells[s.slot] = { status: "loading", label: s.label, variant: s.variant }; });

  const empty = $("#results-area .empty-state"); if (empty) empty.remove();

  // Auto mode always runs a single product (index 0). If the user previewed
  // first, the generate request sends those prompts verbatim (source="raw"
  // server-side) so edits are honored — but we still know from the preview
  // step itself whether they originated from the generic engine, so show
  // that provenance immediately instead of waiting on the SSE source (which
  // will say "raw" in that case, not "generic").
  const knownGeneric = state.mode === "auto" && ev.index === 0 &&
    state.autoPromptsSource === "generic";

  const block = el("div", { class: "product-block", id: `product-${ev.index}` }, [
    el("div", { class: "pb-head" }, [
      el("div", {}, [
        el("span", { class: "pb-name", text: ev.product }),
        el("span", { class: "pb-meta", text: [ev.size, ev.category].filter(Boolean).join(" · ") }),
        el("span", {
          class: "info-tag", id: `pb-source-${ev.index}`,
          text: knownGeneric ? "smart generic template" : "",
          style: knownGeneric ? "margin-left:8px;" : "display:none;margin-left:8px;",
        }),
      ]),
      el("button", { class: "btn btn-sm", id: `dl-prod-${ev.index}`, text: "⬇ Download 4 (ZIP)", disabled: "disabled", onclick: () => downloadProductZip(ev.index) }),
    ]),
    el("div", { class: "grid2", id: `grid-${ev.index}` }, SLOTS.map((s) => buildCellNode(ev.index, s.slot))),
  ]);
  $("#results-area").appendChild(block);
}

function buildCellNode(index, slot) {
  const s = SLOT_BY_KEY[slot];
  return el("div", { class: "img-cell", id: `cell-${index}-${slot}` }, [
    el("div", { class: "img-frame loading", id: `frame-${index}-${slot}` }, [
      el("div", { class: "spinner" }),
      el("div", { class: "ph-msg", id: `ph-${index}-${slot}`, text: "Queued…" }),
    ]),
    el("div", { class: "cell-label" }, [
      el("span", { class: "cl-name", text: s.label }),
      el("span", { class: "cl-status", id: `st-${index}-${slot}`, text: s.variant === "hero" ? "no logo" : "" }),
    ]),
  ]);
}

function getCell(index, slot) { return document.getElementById(`cell-${index}-${slot}`); }

function setCellLoading(index, slot, msg) {
  const frame = $(`#frame-${index}-${slot}`);
  if (!frame) return;
  if (!frame.classList.contains("loading") || frame.classList.contains("errored")) {
    frame.className = "img-frame loading";
    frame.innerHTML = "";
    frame.appendChild(el("div", { class: "spinner" }));
    frame.appendChild(el("div", { class: "ph-msg", id: `ph-${index}-${slot}` }));
  }
  const ph = $(`#ph-${index}-${slot}`); if (ph) ph.textContent = msg || "Generating…";
}

function renderCell(index, slot) {
  const cell = state.results[index]?.cells[slot];
  const frame = $(`#frame-${index}-${slot}`);
  const st = $(`#st-${index}-${slot}`);
  if (!cell || !frame) return;
  frame.innerHTML = "";
  if (cell.status === "ok") {
    frame.className = "img-frame";
    const dataUrl = `data:image/png;base64,${cell.data}`;
    const img = el("img", { src: dataUrl, alt: cell.label, loading: "lazy" });
    img.addEventListener("click", () => openModal(dataUrl, `${state.results[index].product} — ${cell.label}`));
    const dl = el("div", { class: "dl-overlay" }, [
      el("button", { class: "icon-btn", title: "Download", text: "⬇", onclick: (e) => { e.stopPropagation(); downloadSingle(index, slot); } }),
    ]);
    frame.appendChild(img);
    frame.appendChild(dl);
    if (st) st.textContent = cell.variant === "hero" ? "no logo" : "logo ✓";
  } else if (cell.status === "error") {
    frame.className = "img-frame errored";
    frame.appendChild(el("div", { class: "err-card" }, [
      el("div", { class: "ex", text: "⚠" }),
      el("div", { class: "msg", text: cell.error || "Generation failed" }),
      el("button", { class: "btn btn-sm", text: "↻ Retry", onclick: () => retrySlot(index, slot) }),
    ]));
    if (st) st.textContent = "failed";
  }
}

function updateProductActions(index) {
  const res = state.results[index];
  if (!res) return;
  const okCount = Object.values(res.cells).filter((c) => c.status === "ok").length;
  const btn = $(`#dl-prod-${index}`);
  if (btn) btn.disabled = okCount === 0;
}

// ---- Retry a single slot --------------------------------------------------
async function retrySlot(index, slot) {
  if (state.generating) { toast("Wait for the current batch to finish.", "bad"); return; }
  const ctx = state.genContext;
  if (!ctx) { toast("Nothing to retry.", "bad"); return; }
  const job = state.results[index].job;
  setCellLoading(index, slot, "Retrying…");
  const body = {
    provider: ctx.provider, api_key: ctx.api_key, logo_base64: ctx.logo_base64,
    brand_name: ctx.brand_name, dry_run: ctx.dry_run,
    product_name: job.product_name, size: job.size, category: job.category,
    only_slots: [slot],
  };
  if (ctx.mode === "custom") { body.custom_prompts = ctx.custom_prompts; body.custom_negatives = ctx.custom_negatives; }
  else if (ctx.raw_prompts) { body.raw_prompts = ctx.raw_prompts; body.custom_negatives = ctx.custom_negatives; }
  try {
    await streamEvents("/api/generate", body, null, (ev) => handleEvent(ev, true));
    updateProductActions(index);
  } catch (e) {
    toast("Retry failed: " + e.message, "bad");
  }
}

// ---- Downloads ------------------------------------------------------------
function downloadSingle(index, slot) {
  const cell = state.results[index]?.cells[slot];
  if (!cell || cell.status !== "ok") return;
  const res = state.results[index];
  const name = `${slugify(res.product)}_${slugify(res.size)}_${slot}.png`;
  downloadBlob(new Blob([b64ToBytes(cell.data)], { type: "image/png" }), name);
}

function downloadProductZip(index) {
  const res = state.results[index];
  if (!res) return;
  const files = [];
  SLOTS.forEach((s) => {
    const cell = res.cells[s.slot];
    if (cell && cell.status === "ok") files.push({ name: `${s.slot}.png`, data: b64ToBytes(cell.data) });
  });
  if (!files.length) { toast("No completed images for this product yet.", "bad"); return; }
  const zip = window.makeZip(files);
  downloadBlob(zip, `${slugify(res.product)}_${slugify(res.size)}.zip`);
}

function downloadBatchZip() {
  const files = [];
  state.order.forEach((index) => {
    const res = state.results[index];
    const folder = `${slugify(res.product)}_${slugify(res.size)}`;
    SLOTS.forEach((s) => {
      const cell = res.cells[s.slot];
      if (cell && cell.status === "ok") files.push({ name: `${folder}/${s.slot}.png`, data: b64ToBytes(cell.data) });
    });
  });
  if (!files.length) { toast("No completed images to zip yet.", "bad"); return; }
  const zip = window.makeZip(files);
  downloadBlob(zip, `brand_images_${Date.now()}.zip`);
  toast(`Zipped ${files.length} images.`, "ok");
}

// ---- Audit ----------------------------------------------------------------
function renderAudit(ev) {
  const area = $("#audit-area");
  area.innerHTML = "";
  if (ev.passed) {
    area.appendChild(el("div", { class: "audit-badge pass", text: "✓ Uniqueness: PASS — all product concepts distinct" }));
  } else {
    area.appendChild(el("div", { class: "audit-badge warn", text: `⚠ Uniqueness: ${ev.issues.length} issue(s) found` }));
    const ul = el("ul", { class: "audit-issues" });
    ev.issues.forEach((i) => ul.appendChild(el("li", { text: i })));
    area.appendChild(ul);
  }
}

// ---- Modal ----------------------------------------------------------------
function wireModal() {
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
}
function openModal(src, cap) {
  $("#modal-img").src = src;
  $("#modal-cap").textContent = cap || "";
  $("#modal").classList.add("open");
}
function closeModal() { $("#modal").classList.remove("open"); }
