"use strict";
const DEFAULT_API = "http://localhost:8000";
const statusEl = () => document.getElementById("status");

function load() {
  chrome.storage.sync.get(["api_base_url"], (r) => {
    document.getElementById("url").value = (r && r.api_base_url) || DEFAULT_API;
  });
}

function save() {
  const url = document.getElementById("url").value.trim() || DEFAULT_API;
  chrome.storage.sync.set({ api_base_url: url }, () => {
    statusEl().textContent = "Saved ✓";
    setTimeout(() => (statusEl().textContent = ""), 1500);
  });
}

async function test() {
  const url = document.getElementById("url").value.trim() || DEFAULT_API;
  statusEl().textContent = "Testing…";
  try {
    const resp = await fetch(url.replace(/\/$/, "") + "/health");
    const j = await resp.json();
    statusEl().textContent = j.status === "ok"
      ? `Connected ✓  (${j.num_sources} sources, ${j.num_guides} guides, mode ${j.qa_mode})`
      : "Reached server, unexpected response.";
  } catch (e) {
    statusEl().textContent = "Could not reach the API at that URL.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  document.getElementById("save").addEventListener("click", save);
  document.getElementById("test").addEventListener("click", test);
});
