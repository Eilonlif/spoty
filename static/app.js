// Front-end logic: submit a link, poll for progress, reveal the download.

const form = document.getElementById("convert-form");
const urlInput = document.getElementById("url");
const submitBtn = document.getElementById("submit-btn");
const statusBox = document.getElementById("status");
const statusMessage = document.getElementById("status-message");
const statusPercent = document.getElementById("status-percent");
const progressBar = document.getElementById("progress-bar");
const downloadLink = document.getElementById("download-link");

const POLL_MS = 1500;
let pollTimer = null;

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
    const data = await res.json();
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
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${jobId}`);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error || "Lost track of the job.");

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
      clearInterval(pollTimer);
      showError(err.message);
      setBusy(false);
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
}

function finish(jobId, job) {
  statusMessage.textContent = job.message || "Done!";
  statusPercent.textContent = "100%";
  progressBar.style.width = "100%";
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
