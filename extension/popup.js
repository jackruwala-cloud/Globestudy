"use strict";

const DEFAULT_API = "http://localhost:8000";

function getApiBase() {
  return new Promise((resolve) => {
    try {
      chrome.storage.sync.get(["api_base_url"], (r) => resolve((r && r.api_base_url) || DEFAULT_API));
    } catch (e) {
      resolve(DEFAULT_API);
    }
  });
}

function esc(s) {
  return String(s == null ? "" : s)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

// Minimal, safe markdown -> HTML for the answer body (escape first, then format).
function renderMarkdown(md) {
  const lines = esc(md).split("\n");
  let html = "";
  let inList = false;
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (let raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (/^### /.test(line)) { closeList(); html += "<h3>" + line.slice(4) + "</h3>"; }
    else if (/^## /.test(line)) { closeList(); html += "<h2>" + line.slice(3) + "</h2>"; }
    else if (/^\s*[-*] /.test(line)) { if (!inList) { html += "<ul>"; inList = true; } html += "<li>" + line.replace(/^\s*[-*] /, "") + "</li>"; }
    else if (line.trim() === "") { closeList(); html += "<br>"; }
    else { closeList(); html += "<p>" + line + "</p>"; }
  }
  closeList();
  return html;
}

function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

function render(ans, isDemo) {
  const el = document.getElementById("answer");
  const confMap = { high: "High confidence", medium: "Medium confidence", none: "No verified source" };
  let html = '<div class="badges">';
  html += ans.risk_level === "HIGH" ? badge("⚠ High-stakes", "risk-high") : badge("General info", "risk-low");
  html += badge(confMap[ans.confidence] || ans.confidence, ans.confidence);
  if (isDemo) html += badge("demo data", "demo");
  html += "</div>";

  if (ans.coverage) html += `<div class="coverage">${esc(ans.coverage)}</div>`;
  if (ans.high_stakes_notice) html += `<div class="notice">${esc(ans.high_stakes_notice)}</div>`;
  html += `<div class="body">${renderMarkdown(ans.answer_markdown || "")}</div>`;

  if (ans.citations && ans.citations.length) {
    html += '<div class="sources"><h4>Sources (verify at the official page):</h4>';
    for (const c of ans.citations) {
      html += `<div>[${c.n}] <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.source_title)}${c.section ? " — " + esc(c.section) : ""}</a>` +
              `<div class="src-meta">${esc(c.publisher || "")}${c.retrieved_date ? " · retrieved " + esc(c.retrieved_date) : ""}</div></div>`;
    }
    html += "</div>";
  }
  if (ans.referrals && ans.referrals.length) {
    html += '<div class="referrals"><strong>Who to ask instead:</strong><ul>';
    for (const r of ans.referrals) html += `<li>${esc(r)}</li>`;
    html += "</ul></div>";
  }
  el.innerHTML = html;
}

// Fallback demo answer so the popup is useful even if the API is unreachable.
function demoAnswer(q) {
  return {
    question: q, answered: false, confidence: "none", coverage: "Demo mode — API not reachable.",
    answer_markdown: "**Can't reach the API.** Set your API base URL in ⚙️ Settings (deploy it or run a tunnel). This is placeholder demo content.",
    citations: [], referrals: ["Set the API base URL in Settings, then try again."],
    risk_level: "HIGH", high_stakes_notice: null,
  };
}

async function ask() {
  const q = document.getElementById("q").value.trim();
  if (!q) return;
  const statusEl = document.getElementById("status");
  document.getElementById("answer").innerHTML = "";
  statusEl.textContent = "Searching primary sources…";
  const base = await getApiBase();
  try {
    const resp = await fetch(base.replace(/\/$/, "") + "/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const ans = await resp.json();
    statusEl.textContent = "";
    render(ans, false);
  } catch (e) {
    statusEl.textContent = "";
    render(demoAnswer(q), true);
  }
}

// Voice input via Web Speech API.
function setupMic() {
  const micBtn = document.getElementById("mic");
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { micBtn.disabled = true; micBtn.title = "Voice not supported in this browser"; return; }
  const rec = new SR();
  rec.lang = "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
  let recording = false;
  micBtn.addEventListener("click", () => {
    if (recording) { rec.stop(); return; }
    try { rec.start(); recording = true; micBtn.classList.add("recording"); }
    catch (e) { /* already started */ }
  });
  rec.onresult = (ev) => {
    const t = ev.results[0][0].transcript;
    const qEl = document.getElementById("q");
    qEl.value = (qEl.value ? qEl.value + " " : "") + t;
  };
  rec.onend = () => { recording = false; micBtn.classList.remove("recording"); };
  rec.onerror = () => { recording = false; micBtn.classList.remove("recording"); };
}

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("ask").addEventListener("click", ask);
  document.getElementById("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
  });
  document.getElementById("settingsLink").addEventListener("click", (e) => {
    e.preventDefault();
    if (chrome.runtime && chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
  });
  setupMic();
  const base = await getApiBase();
  document.getElementById("apiLabel").textContent = "API: " + base;
});
