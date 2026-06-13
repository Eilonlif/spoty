// Front-end logic: submit a link, poll for progress, reveal the download.

const form = document.getElementById("convert-form");
const urlInput = document.getElementById("url");
const submitBtn = document.getElementById("submit-btn");
const statusBox = document.getElementById("status");
const statusMessage = document.getElementById("status-message");
const statusPercent = document.getElementById("status-percent");
const progressBar = document.getElementById("progress-bar");
const downloadLink = document.getElementById("download-link");
const meta = document.getElementById("meta");
const metaArt = document.getElementById("meta-art");
const metaTitle = document.getElementById("meta-title");
const metaSub = document.getElementById("meta-sub");
const etaEl = document.getElementById("eta");

const POLL_MS = 1500;
// How many consecutive polling failures (e.g. a server restart, a dropped
// connection, an empty response) to tolerate before giving up.
const MAX_POLL_RETRIES = 5;
let pollTimer = null;

// Parse a fetch Response as JSON, tolerating empty/non-JSON bodies instead of
// throwing the opaque "Unexpected end of JSON input".
async function readJson(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { error: `Unexpected server response (HTTP ${res.status}).` };
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  resetStatus();
  setBusy(true);
  showStatus("Starting...", 0);

  try {
    const res = await fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(data.error || "Could not start the conversion.");
    }
    pollStatus(data.id);
  } catch (err) {
    showError(err.message);
    setBusy(false);
  }
});

function pollStatus(jobId) {
  clearInterval(pollTimer);
  let retries = 0;
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${jobId}`);
      const job = await readJson(res);
      if (!res.ok) throw new Error(job.error || "Lost track of the job.");

      retries = 0; // a good response resets the failure counter
      updateProgress(job);

      if (job.status === "done") {
        clearInterval(pollTimer);
        finish(jobId, job);
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        showError(job.error || job.message);
        setBusy(false);
      }
    } catch (err) {
      // Transient failure (server restart, network blip): retry a few times
      // before surfacing the error, so a momentary hiccup doesn't kill a job.
      retries += 1;
      if (retries > MAX_POLL_RETRIES) {
        clearInterval(pollTimer);
        showError(`${err.message} (giving up after ${MAX_POLL_RETRIES} retries)`);
        setBusy(false);
      }
    }
  }, POLL_MS);
}

function updateProgress(job) {
  const pct = job.progress || 0;
  statusMessage.innerHTML = `<span class="spin"></span>${escapeHtml(
    job.message || "Working..."
  )}`;
  statusPercent.textContent = `${pct}%`;
  progressBar.style.width = `${pct}%`;
  renderMeta(job);
  etaEl.textContent = etaText(job);
}

// Show the cover art + title + track count once the link has resolved.
function renderMeta(job) {
  if (!job.title) return;
  metaTitle.textContent = job.title;
  const parts = [];
  if (job.total) parts.push(`${job.total} track${job.total === 1 ? "" : "s"}`);
  metaSub.textContent = parts.join(" · ");
  if (job.image_url) {
    metaArt.src = job.image_url;
    metaArt.style.display = "";
  } else {
    metaArt.style.display = "none";
  }
  meta.classList.remove("hidden");
}

function etaText(job) {
  if (job.eta_seconds == null) return "";
  if (job.eta_seconds <= 0) return "Finishing up…";
  return `~${formatDuration(job.eta_seconds)} remaining`;
}

function formatDuration(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function finish(jobId, job) {
  renderMeta(job);
  statusMessage.textContent = job.message || "Done!";
  statusPercent.textContent = "100%";
  progressBar.style.width = "100%";
  etaEl.textContent = "";
  downloadLink.href = `/api/download/${jobId}`;
  downloadLink.textContent = `⬇ Download ${job.result_name || "file"}`;
  downloadLink.classList.remove("hidden");
  setBusy(false);
}

function showStatus(message, pct) {
  statusBox.classList.remove("hidden", "error");
  statusMessage.textContent = message;
  statusPercent.textContent = `${pct}%`;
  progressBar.style.width = `${pct}%`;
}

function showError(message) {
  statusBox.classList.remove("hidden");
  statusBox.classList.add("error");
  statusMessage.textContent = `⚠ ${message}`;
  statusPercent.textContent = "";
}

function resetStatus() {
  statusBox.classList.remove("error");
  downloadLink.classList.add("hidden");
  meta.classList.add("hidden");
  metaArt.removeAttribute("src");
  etaEl.textContent = "";
}

function setBusy(busy) {
  submitBtn.disabled = busy;
  urlInput.disabled = busy;
  submitBtn.textContent = busy ? "Working..." : "Convert";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
