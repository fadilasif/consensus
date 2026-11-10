const app = document.querySelector("#app");

const STAGES = [
  {
    key: "collecting",
    title: "Collecting comments",
    description: "Pulling the video metadata, top-level comments, and their embedded replies.",
    status: "Collecting top-level comments…",
  },
  {
    key: "cleaning",
    title: "Cleaning and analysing",
    description: "Removing noise and measuring engagement across the thread.",
    status: "Cleaning and measuring the thread…",
  },
  {
    key: "classifying",
    title: "Classifying audience feedback",
    description: "Applying a question-specific framework to every top-level comment.",
    status: "Classifying audience feedback…",
  },
  {
    key: "generating",
    title: "Generating audience intelligence",
    description: "Comparing the distribution and writing the brief.",
    status: "Writing the audience brief…",
  },
];

const TONES = {
  BUY_NOW: "#e8b464",
  WAIT_OR_SAMPLE: "#a9bfa2",
  AVOID_PURCHASE: "#c98e7f",
  DOUBT_DUE_TO_REVIEWER_CREDIBILITY: "#8d9bb0",
  UNDECIDED_OR_NEUTRAL: "#a8a49b",
  IRRELEVANT: "#3b3b3d",
};

const FALLBACK_TONES = ["#e8b464", "#a9bfa2", "#c98e7f", "#8d9bb0", "#a8a49b", "#3b3b3d"];

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  view: "home",
  form: { url: "", question: "" },
  notice: "",
  run: null,
  result: null,
  token: 0,
};

const ICONS = {
  play: `<svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="2.75" y="5" width="18.5" height="14" rx="3"/><path d="M10.2 9.2l4.6 2.8-4.6 2.8V9.2z" fill="currentColor" stroke="none"/></svg>`,
  arrowRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 12h15"/><path d="M13 6l6 6-6 6"/></svg>`,
  arrowLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M20 12H5"/><path d="M11 6l-6 6 6 6"/></svg>`,
  external: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M14 4h6v6"/><path d="M20 4l-8 8"/><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12 4v11"/><path d="M8 11l4 4 4-4"/><path d="M5 19h14"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 12l4 4L19 6"/></svg>`,
};

const LOGO = `<svg class="brand-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true" focusable="false"><circle cx="9.1" cy="12" r="6.1"/><circle cx="14.9" cy="12" r="6.1" opacity=".52"/><circle class="brand-dot" cx="12" cy="12" r="1.35" fill="#e8b464" stroke="none"/></svg>`;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character];
  });
}

function displayUrl(value) {
  return String(value || "")
    .replace(/^https?:\/\//i, "")
    .replace(/\/$/, "");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return new Intl.NumberFormat("en-US").format(numeric);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric.toFixed(1).replace(/\.0$/, "")}%`;
}

function formatDate(value) {
  if (!value) return "Undated";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Undated";
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function toneFor(key, index) {
  return TONES[key] || FALLBACK_TONES[index % FALLBACK_TONES.length];
}

function parseYouTubeUrl(input) {
  let raw = String(input || "").trim();
  if (!raw) return null;

  if (/^[A-Za-z0-9_-]{11}$/.test(raw)) {
    return { videoId: raw, url: `https://www.youtube.com/watch?v=${raw}` };
  }

  if (!/^https?:\/\//i.test(raw)) raw = `https://${raw}`;

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }

  let host = parsed.hostname.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);

  let videoId = null;

  if (["youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"].includes(host)) {
    if (parsed.pathname === "/watch") {
      videoId = parsed.searchParams.get("v");
    } else if (/^\/(shorts|embed|live)\//.test(parsed.pathname)) {
      videoId = parsed.pathname.split("/").filter(Boolean)[1] || null;
    }
  } else if (host === "youtu.be") {
    videoId = parsed.pathname.split("/").filter(Boolean)[0] || null;
  }

  if (!videoId || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) return null;

  return { videoId, url: parsed.toString() };
}

function renderNav(mode) {
  const labels = {
    home: "Local tool",
    progress: "Analysis running",
    loading: "Opening brief",
    error: "Analysis stopped",
    result: "Audience brief",
  };

  return `
    <header class="site-nav">
      <div class="wrap nav-inner">
        <button class="brand brand-button" type="button" data-action="home" aria-label="Consensus home">
          ${LOGO}
          <span class="brand-word">Consensus</span>
        </button>
        <nav class="nav-links" aria-label="Primary">
          <span class="nav-meta">${escapeHtml(labels[mode] || labels.home)}</span>
        </nav>
      </div>
    </header>
  `;
}

function renderFooter() {
  return `
    <footer class="site-footer">
      <div class="wrap footer-inner">
        <div class="footer-brand">
          ${LOGO}
          <span>Consensus</span>
        </div>
        <p class="footer-note">A local audience intelligence tool. Public comments, read carefully. API keys stay on this machine.</p>
      </div>
    </footer>
  `;
}

function homeTemplate() {
  return `
    ${renderNav("home")}
    <main id="main">
      <section class="hero">
        <div class="wrap hero-grid">
          <div class="hero-copy">
            <p class="eyebrow">Audience intelligence for YouTube</p>
            <h1>What does the audience <em>actually</em> think?</h1>
            <p class="lede">Paste a video and a question. Consensus reads every top-level comment, maps the room, and writes a brief you can use.</p>
          </div>

          <div class="hero-form">
            <p class="form-kicker">Start an analysis</p>
            <form class="analysis-form" id="analysis-form" novalidate>
              <div class="field">
                <label for="video-url">YouTube video</label>
                <div class="input-shell" data-field-shell="url">
                  ${ICONS.play}
                  <input
                    id="video-url"
                    name="video-url"
                    type="text"
                    inputmode="url"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="https://www.youtube.com/watch?v=..."
                    aria-describedby="url-hint form-error"
                    aria-required="true"
                  />
                </div>
                <p class="field-hint" id="url-hint">Paste a watch, share, Shorts, or live link.</p>
              </div>

              <div class="field">
                <label for="question">Your research question</label>
                <div class="input-shell" data-field-shell="question">
                  <input
                    id="question"
                    name="question"
                    type="text"
                    autocomplete="off"
                    maxlength="500"
                    placeholder="Should I buy it?"
                    aria-describedby="form-error"
                    aria-required="true"
                  />
                </div>
              </div>

              <button class="button form-submit" type="submit">
                <span>Analyse video</span>
                ${ICONS.arrowRight}
              </button>

              <p class="form-note">Top-level comments only. Replies are never classified.</p>
              <p class="form-error" id="form-error" role="alert" hidden></p>
              ${state.notice ? `<p class="notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
            </form>

            <div class="stage-strip" aria-hidden="true">
              <span>Collect</span><i></i>
              <span>Clean</span><i></i>
              <span>Classify</span><i></i>
              <span>Write</span>
              <span class="stage-time">Usually a few minutes</span>
            </div>
          </div>
        </div>
      </section>
    </main>
    ${renderFooter()}
  `;
}

function renderHome() {
  document.title = "Consensus — What does the audience actually think?";
  app.innerHTML = homeTemplate();

  const urlInput = document.getElementById("video-url");
  const questionInput = document.getElementById("question");

  if (urlInput) urlInput.value = state.form.url;
  if (questionInput) questionInput.value = state.form.question;
}

function progressTemplate() {
  const run = state.run || {};
  const stageIndex = activeStageIndex();
  const fillWidth = stageIndex >= STAGES.length ? 100 : [12, 38, 64, 90][stageIndex];

  return `
    ${renderNav("progress")}
    <main id="main" class="view progress-view">
      <div class="wrap narrow">
        <div class="view-top">
          <button class="text-button" type="button" data-action="cancel">
            ${ICONS.arrowLeft}
            <span>Cancel analysis</span>
          </button>
          <span class="mono">Consensus / Running</span>
        </div>

        <div class="progress-head">
          <p class="eyebrow">Analysis in progress</p>
          <h1 class="progress-title">Reading the room.</h1>
          <p class="progress-video" id="progress-video">${escapeHtml(displayUrl(run.url || ""))}</p>
          <p class="progress-question">“${escapeHtml(run.question || "")}”</p>
        </div>

        <div class="progress-panel">
          <div class="progress-rail" aria-hidden="true">
            <span class="progress-fill" id="progress-fill" style="width:${fillWidth}%"></span>
          </div>
          <ol class="stage-list">
            ${STAGES.map(
              (stage, index) => `
                <li class="stage-item ${index === stageIndex ? "is-active" : ""}" data-stage="${stage.key}" data-index="${index}" ${index === stageIndex ? 'aria-current="step"' : ""}>
                  <span class="stage-index">${String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h2>${stage.title}</h2>
                    <p>${stage.description}</p>
                  </div>
                  <span class="stage-state">${index === stageIndex ? "Running" : "Waiting"}</span>
                </li>
              `,
            ).join("")}
          </ol>
        </div>

        <p class="progress-note" id="progress-note" role="status" aria-live="polite">${STAGES[stageIndex]?.status || "Working…"}</p>
        <p class="progress-help">This can take a few minutes. Keep this tab open.</p>
      </div>
    </main>
  `;
}

function activeStageIndex() {
  const stage = state.run?.stage;
  if (stage === "saved") return STAGES.length;
  const index = STAGES.findIndex((item) => item.key === stage);
  return index < 0 ? 0 : index;
}

function renderProgress() {
  document.title = "Analysing — Consensus";
  app.innerHTML = progressTemplate();
  updateProgress();
  focusMain();
  window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function updateProgress() {
  if (state.view !== "progress") return;

  const items = Array.from(document.querySelectorAll(".stage-item"));
  if (!items.length) return;

  const stage = state.run?.stage;
  const stageIndex = activeStageIndex();
  const complete = stage === "saved";

  items.forEach((item, index) => {
    const done = complete || index < stageIndex;
    const active = !complete && index === stageIndex;

    item.classList.toggle("is-done", done);
    item.classList.toggle("is-active", active);

    if (active) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");

    const stateLabel = item.querySelector(".stage-state");
    if (stateLabel) {
      if (done) stateLabel.innerHTML = `${ICONS.check}<span>Done</span>`;
      else if (active) stateLabel.textContent = "Running";
      else stateLabel.textContent = "Waiting";
    }
  });

  const fill = document.getElementById("progress-fill");
  if (fill) fill.style.width = complete ? "100%" : `${[12, 38, 64, 90][stageIndex]}%`;

  const note = document.getElementById("progress-note");
  if (note) {
    note.textContent = complete
      ? "Brief ready. Opening it now."
      : STAGES[stageIndex]?.status || "Working…";
  }
}

function updateProgressMeta() {
  if (state.view !== "progress" || !state.run?.video) return;
  const line = document.getElementById("progress-video");
  if (line) {
    line.textContent = state.run.video.title;
    line.title = state.run.url;
  }
}

function loadingTemplate() {
  return `
    ${renderNav("loading")}
    <main id="main" class="view loading-view">
      <div class="wrap narrow">
        <div class="loading-inner">
          <div class="loading-line" aria-hidden="true"></div>
          <h1 class="loading-title">Opening brief</h1>
        </div>
      </div>
    </main>
  `;
}

function renderLoading() {
  document.title = "Opening brief — Consensus";
  app.innerHTML = loadingTemplate();
  focusMain();
}

function errorTemplate() {
  const error = state.run?.error || {};
  return `
    ${renderNav("error")}
    <main id="main" class="view error-view">
      <div class="wrap narrow">
        <div class="view-top">
          <button class="text-button" type="button" data-action="home">
            ${ICONS.arrowLeft}
            <span>Start over</span>
          </button>
          <span class="mono">Consensus / Stopped</span>
        </div>
        <div class="error-head">
          <p class="eyebrow">Analysis stopped</p>
          <h1 class="error-title">We couldn’t finish this one.</h1>
        </div>
        <div class="error-card" role="alert">
          <p class="error-message">${escapeHtml(error.message || "The analysis stopped before it could finish.")}</p>
          ${error.hint ? `<p class="error-hint">${escapeHtml(error.hint)}</p>` : ""}
        </div>
        <div class="error-actions">
          ${state.run?.url ? `<button class="button" type="button" data-action="retry">Try again ${ICONS.arrowRight}</button>` : ""}
          <button class="text-button" type="button" data-action="home">Choose another video</button>
        </div>
      </div>
    </main>
  `;
}

function renderError() {
  document.title = "Analysis stopped — Consensus";
  app.innerHTML = errorTemplate();
  focusMain();
  window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function resultTemplate(result) {
  const distribution = Array.isArray(result.distribution) ? result.distribution : [];
  const totalPercentage = distribution.reduce((sum, item) => sum + (Number(item.percentage) || 0), 0);
  const comments = Array.isArray(result.topComments) ? result.topComments : [];
  const relevance = result.relevance || {};
  const scope = result.scope || {};
  const video = result.video || {};
  const report = result.report || {};
  const generated = formatDate(report.generatedAt);

  const stacked = distribution
    .map(
      (item, index) =>
        `<span style="width:${Number(item.percentage) || 0}%;background:${toneFor(item.key, index)}" title="${escapeHtml(item.label)} · ${formatPercent(item.percentage)}"></span>`,
    )
    .join("");

  const distributionRows = distribution
    .map(
      (item, index) => `
        <li class="dist-row" style="--tone:${toneFor(item.key, index)};--width:${Number(item.percentage) || 0}%">
          <div class="dist-top">
            <span class="dist-swatch" aria-hidden="true"></span>
            <span class="dist-label">${escapeHtml(item.label)}</span>
            <span class="dist-count">${formatNumber(item.count)}</span>
            <span class="dist-percent">${formatPercent(item.percentage)}</span>
          </div>
          <div class="dist-track" aria-hidden="true"><i></i></div>
        </li>
      `,
    )
    .join("");

  const commentRows = comments
    .map(
      (comment, index) => `
        <li class="comment-item">
          <span class="comment-rank">${String(index + 1).padStart(2, "0")}</span>
          <span class="comment-text">${escapeHtml(comment.comment)}</span>
          <span class="comment-likes">${formatNumber(comment.likes)} <span>likes</span></span>
        </li>
      `,
    )
    .join("");

  const distributionLabel = distribution.length
    ? distribution.map((item) => `${item.label} ${formatPercent(item.percentage)}`).join(", ")
    : "No classification distribution available.";

  return `
    ${renderNav("result")}
    <main id="main" class="view result-view">
      <div class="wrap">
        <div class="view-top">
          <button class="text-button" type="button" data-action="home">
            ${ICONS.arrowLeft}
            <span>New analysis</span>
          </button>
          <span class="mono">Audience brief / ${escapeHtml(generated)}</span>
        </div>

        <header class="result-head">
          <p class="eyebrow">Audience brief</p>
          <h1 class="result-title">${escapeHtml(video.title || "Untitled YouTube video")}</h1>
          <p class="result-question">
            <span>Question</span>
            <em>“${escapeHtml(result.question || "Untitled question")}”</em>
            ${
              video.url
                ? `<a class="result-link" href="${escapeHtml(video.url)}" target="_blank" rel="noopener noreferrer">Open on YouTube ${ICONS.external}</a>`
                : ""
            }
          </p>

          <div class="metrics">
            <div class="metric">
              <span class="metric-label">Views</span>
              <span class="metric-value">${formatNumber(video.views)}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Video likes</span>
              <span class="metric-value">${formatNumber(video.likes)}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Comments</span>
              <span class="metric-value">${formatNumber(video.comments)}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Replies</span>
              <span class="metric-value">${formatNumber(video.replies)}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Classified</span>
              <span class="metric-value">${formatNumber(relevance.classified)}</span>
            </div>
          </div>
        </header>

        <div class="result-grid">
          <div class="result-main">
            <section class="section-block" aria-labelledby="reading-heading">
              <div class="section-head">
                <h2 id="reading-heading">The reading</h2>
                <span class="mono">${escapeHtml(report.model || "Groq")}${report.reasoning ? ` · ${escapeHtml(report.reasoning)}` : ""}</span>
              </div>
              <div class="report-prose">${renderMarkdown(report.text || "")}</div>
            </section>

            <section class="section-block" aria-labelledby="comments-heading">
              <div class="section-head">
                <h2 id="comments-heading">Most-liked comments</h2>
                <span class="mono">Top ${Math.min(comments.length, 10)} by likes</span>
              </div>
              ${
                comments.length
                  ? `<ol class="comment-list">${commentRows}</ol>`
                  : `<p class="source-note">No top-level comments were available for this analysis.</p>`
              }
            </section>
          </div>

          <aside class="result-aside" aria-label="Audience distribution and export">
            <section class="aside-block" aria-labelledby="distribution-heading">
              <div class="section-head">
                <h2 id="distribution-heading">Audience distribution</h2>
                <span class="mono">${formatNumber(relevance.classified)} classified</span>
              </div>

              ${
                distribution.length
                  ? `
                    <div class="stacked-bar" role="img" aria-label="${escapeHtml(distributionLabel)}">${stacked}</div>
                    <p class="relevance-line"><strong>${formatNumber(relevance.relevant)} of ${formatNumber(relevance.classified)}</strong> top-level comments were relevant (${formatPercent(relevance.relevantPercentage)}).</p>
                    <ul class="distribution-list">${distributionRows}</ul>
                  `
                  : `<p class="source-note">No classification distribution was available for this brief.</p>`
              }
            </section>

            <section class="aside-block" aria-labelledby="export-heading">
              <h2 id="export-heading">Export</h2>
              <div class="export-actions">
                <button class="button" type="button" data-action="export-md">
                  <span>Download brief</span>
                  ${ICONS.download}
                </button>
                <button class="text-button" type="button" data-action="export-json">Download JSON</button>
              </div>
              <p class="export-note">Markdown includes the narrative, distribution, and most-liked comments.</p>
              <p class="source-note" id="export-status" role="status" aria-live="polite"></p>
            </section>
          </aside>
        </div>

        <footer class="result-footer">
          <p>This brief describes the comments in this dataset. It does not speak for the entire viewing audience, and likes are not agreement.</p>
          <span class="mono">Consensus${report.model ? ` / ${escapeHtml(report.model)}` : ""} / ${escapeHtml(generated)}</span>
        </footer>
      </div>
    </main>
  `;
}

function renderResult() {
  document.title = `${state.result?.video?.title || "Audience brief"} — Consensus`;
  app.innerHTML = resultTemplate(state.result || {});
  focusMain();
  window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function render() {
  if (state.view === "home") renderHome();
  else if (state.view === "progress") renderProgress();
  else if (state.view === "loading") renderLoading();
  else if (state.view === "error") renderError();
  else if (state.view === "result") renderResult();
}

function focusMain() {
  const target = document.querySelector("#main h1, #main .loading-title");
  if (!target) return;
  target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
  // Restore programmatic scroll if focus moved it
  if (window.scrollY !== 0) window.scrollTo(0, 0);
}

function setView(view, { scroll = true } = {}) {
  state.view = view;
  render();
  if (scroll) window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function goHome({ notice = "" } = {}) {
  if (state.run?.controller) state.run.controller.abort();
  state.token += 1;
  state.run = null;
  state.result = null;
  state.notice = notice;
  state.view = "home";

  if (location.hash) {
    history.pushState({}, "", `${location.pathname}${location.search}`);
  }

  render();
  window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function showError(error) {
  state.run = state.run || {};
  state.run.error = error;
  state.view = "error";
  render();
}

function submitForm() {
  const urlInput = document.getElementById("video-url");
  const questionInput = document.getElementById("question");
  const parsed = parseYouTubeUrl(urlInput?.value || "");
  const question = (questionInput?.value || "").trim();

  if (!parsed) {
    showFormError("Paste a valid YouTube video link.", "url");
    return;
  }

  if (!question) {
    showFormError("Add a research question before starting.", "question");
    return;
  }

  if (question.length > 500) {
    showFormError("Keep the research question under 500 characters.", "question");
    return;
  }

  state.form = { url: parsed.url, question };
  state.notice = "";
  state.result = null;
  state.run = {
    url: parsed.url,
    question,
    videoId: parsed.videoId,
    stage: "collecting",
    video: null,
    controller: null,
    error: null,
  };

  history.pushState({}, "", `${location.pathname}${location.search}#/`);
  setView("progress");
  void startAnalysis();
}

function showFormError(message, field) {
  const error = document.getElementById("form-error");
  if (error) {
    error.hidden = false;
    error.textContent = message;
  }

  const shell = document.querySelector(`[data-field-shell="${field}"]`);
  if (shell) shell.classList.add("is-invalid");

  const input = document.getElementById(field === "url" ? "video-url" : "question");
  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.focus();
  }
}

function clearFormError() {
  const error = document.getElementById("form-error");
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }

  document.querySelectorAll("[data-field-shell]").forEach((shell) => {
    shell.classList.remove("is-invalid");
  });

  document.querySelectorAll("#video-url, #question").forEach((input) => {
    input.removeAttribute("aria-invalid");
  });
}

async function startAnalysis() {
  const run = state.run;
  if (!run) return;

  const controller = new AbortController();
  run.controller = controller;

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify({ url: run.url, question: run.question }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let message = "The analysis could not start.";
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch {
        // Keep the generic message.
      }
      throw new Error(message);
    }

    if (!response.body) throw new Error("The analysis stream was unavailable.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;

    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");

      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);

        if (line) {
          const outcome = handleStreamEvent(JSON.parse(line), run);
          if (outcome === "done" || outcome === "error" || outcome === "stale") {
            finished = true;
            break;
          }
        }

        newline = buffer.indexOf("\n");
      }
    }

    if (!finished && state.run === run && state.view === "progress") {
      showError({
        message: "The analysis ended before a brief was returned.",
        hint: "Try again. If it keeps happening, check the terminal output from the bridge.",
      });
    }
  } catch (error) {
    if (error.name === "AbortError" || state.run !== run) return;

    showError({
      message: error.message || "The analysis could not start.",
      hint: "Check the video link and your API keys, then try again.",
    });
  } finally {
    if (state.run === run) run.controller = null;
  }
}

function handleStreamEvent(event, run) {
  if (!event || typeof event !== "object") return;
  if (state.run !== run) return "stale";

  if (event.type === "started") {
    run.videoId = event.videoId;
    return;
  }

  if (event.type === "stage") {
    run.stage = event.stage;
    updateProgress();
    return;
  }

  if (event.type === "meta") {
    run.video = event.video;
    updateProgressMeta();
    return;
  }

  if (event.type === "error") {
    run.error = { message: event.message, hint: event.hint };
    state.view = "error";
    render();
    return "error";
  }

  if (event.type === "done") {
    const data = event.data;
    if (!data) return "error";

    state.result = data;
    state.view = "result";
    history.pushState({}, "", `#/brief/${data.videoId}/${data.questionKey}`);
    render();
    return "done";
  }

  if (event.type === "ping") return;
}

async function openBrief(videoId, questionKey, { historyMode = "push" } = {}) {
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId) || !/^[a-f0-9]{16}$/.test(questionKey)) {
    goHome();
    return;
  }

  const token = ++state.token;

  if (state.run?.controller) state.run.controller.abort();
  state.run = null;

  state.view = "loading";
  render();

  try {
    const response = await fetch(
      `/api/briefs/${encodeURIComponent(videoId)}/${encodeURIComponent(questionKey)}`,
      { headers: { Accept: "application/json" } },
    );

    if (token !== state.token) return;
    if (!response.ok) throw new Error("That brief could not be opened.");

    const payload = await response.json();
    if (token !== state.token) return;
    if (!payload.brief) throw new Error("That brief could not be opened.");

    state.result = payload.brief;
    state.view = "result";

    if (historyMode === "push") {
      history.pushState({}, "", `#/brief/${videoId}/${questionKey}`);
    }

    render();
  } catch (error) {
    if (token !== state.token) return;

    state.run = {
      error: {
        message: error.message || "That brief could not be opened.",
        hint: "It may have been moved or removed from the local data directory.",
      },
    };
    state.view = "error";
    render();
  }
}

function routeFromLocation({ historyMode = "none" } = {}) {
  const hash = location.hash || "";
  const briefMatch = hash.match(/^#\/brief\/([A-Za-z0-9_-]{11})\/([a-f0-9]{16})$/);

  if (briefMatch) {
    void openBrief(briefMatch[1], briefMatch[2], { historyMode });
    return;
  }

  if (state.view === "progress" && state.run?.controller) {
    state.run.controller.abort();
    state.run = null;
  }

  state.token += 1;
  state.view = "home";
  state.result = null;
  render();
}

function inlineMarkdown(text) {
  let output = escapeHtml(text);
  output = output.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  output = output.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  output = output.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  return output;
}

function parseTableRow(line) {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line) {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line.trim());
}

function renderMarkdown(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!source) return "<p>No narrative was generated for this brief.</p>";

  const lines = source.split("\n");
  const output = [];
  let paragraph = [];
  let listType = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    output.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) return;
    output.push(`</${listType}>`);
    listType = null;
  };

  const openList = (type) => {
    if (listType === type) return;
    closeList();
    output.push(`<${type}>`);
    listType = type;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();

    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }

    if (
      line.startsWith("|") &&
      index + 1 < lines.length &&
      isTableSeparator(lines[index + 1])
    ) {
      flushParagraph();
      closeList();

      const header = parseTableRow(line);
      const rows = [];
      let cursor = index + 2;

      while (cursor < lines.length && lines[cursor].trim().startsWith("|")) {
        rows.push(parseTableRow(lines[cursor]));
        cursor += 1;
      }

      output.push(
        `<div class="table-wrap"><table><thead><tr>${header
          .map((cell) => `<th>${inlineMarkdown(cell)}</th>`)
          .join("")}</tr></thead><tbody>${rows
          .map(
            (row) =>
              `<tr>${row
                .map((cell) => `<td>${inlineMarkdown(cell)}</td>`)
                .join("")}</tr>`,
          )
          .join("")}</tbody></table></div>`,
      );

      index = cursor - 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const tag = heading[1].length <= 2 ? "h3" : "h4";
      output.push(`<${tag}>${inlineMarkdown(heading[2])}</${tag}>`);
      continue;
    }

    if (/^---+$/.test(line)) {
      flushParagraph();
      closeList();
      output.push("<hr />");
      continue;
    }

    if (line.startsWith(">")) {
      flushParagraph();
      closeList();
      output.push(`<blockquote><p>${inlineMarkdown(line.replace(/^>\s?/, ""))}</p></blockquote>`);
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.*)$/);
    if (unordered) {
      flushParagraph();
      openList("ul");
      output.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = line.match(/^\d+[.)]\s+(.*)$/);
    if (ordered) {
      flushParagraph();
      openList("ol");
      output.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
  closeList();

  return output.join("\n");
}

function buildMarkdown(result) {
  const distribution = Array.isArray(result.distribution) ? result.distribution : [];
  const comments = Array.isArray(result.topComments) ? result.topComments : [];
  const relevance = result.relevance || {};
  const report = result.report || {};
  const lines = [];

  lines.push(`# ${result.video?.title || "Audience brief"}`, "");
  lines.push(`**Question:** ${result.question || "—"}`);
  lines.push(`**Generated:** ${formatDate(report.generatedAt)}`);
  lines.push(`**Model:** ${report.model || "—"}${report.reasoning ? ` (${report.reasoning})` : ""}`, "");

  lines.push("## Audience intelligence", "");
  lines.push((report.text || "No narrative was generated.").trim(), "");

  lines.push("## Classification distribution", "");
  lines.push("| Category | Comments | Share |");
  lines.push("| --- | ---: | ---: |");

  for (const item of distribution) {
    lines.push(`| ${item.label} | ${formatNumber(item.count)} | ${formatPercent(item.percentage)} |`);
  }

  lines.push("");
  lines.push(
    `Relevant: ${formatNumber(relevance.relevant)} of ${formatNumber(relevance.classified)} top-level comments (${formatPercent(relevance.relevantPercentage)}).`,
  );
  lines.push(
    `Irrelevant: ${formatNumber(relevance.irrelevant)} (${formatPercent(relevance.irrelevantPercentage)}).`,
    "",
  );

  lines.push("## Most-liked comments", "");

  if (comments.length) {
    comments.forEach((comment, index) => {
      lines.push(`${index + 1}. **${formatNumber(comment.likes)} likes** — ${comment.comment}`);
    });
  } else {
    lines.push("No top-level comments were available.");
  }

  lines.push("");
  lines.push(
    "Likes indicate engagement, not agreement. The most-liked comments are context, not a representative sample.",
  );

  return `${lines.join("\n")}\n`;
}

function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function exportBrief(kind) {
  const result = state.result;
  if (!result) return;

  const stem = `consensus-${result.videoId}-${result.questionKey}-brief`;

  if (kind === "json") {
    downloadFile(`${stem}.json`, `${JSON.stringify(result, null, 2)}\n`, "application/json");
  } else {
    downloadFile(`${stem}.md`, buildMarkdown(result), "text/markdown;charset=utf-8");
  }

  const status = document.getElementById("export-status");
  if (status) {
    status.textContent = kind === "json" ? "JSON downloaded." : "Brief downloaded.";
    window.setTimeout(() => {
      if (status) status.textContent = "";
    }, 2400);
  }
}

document.addEventListener("submit", (event) => {
  if (event.target?.id !== "analysis-form") return;
  event.preventDefault();
  submitForm();
});

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;

  if (target.id === "video-url") state.form.url = target.value;
  if (target.id === "question") state.form.question = target.value;

  if (state.notice) state.notice = "";
  clearFormError();
});

document.addEventListener("click", (event) => {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) return;

  const action = actionTarget.dataset.action;

  if (action === "home") {
    event.preventDefault();
    goHome();
    return;
  }

  if (action === "cancel") {
    event.preventDefault();
    goHome({ notice: "Analysis cancelled." });
    return;
  }

  if (action === "retry") {
    event.preventDefault();
    if (!state.run?.url) {
      goHome();
      return;
    }

    state.run = {
      ...state.run,
      error: null,
      stage: "collecting",
      video: null,
      controller: null,
    };
    setView("progress");
    void startAnalysis();
    return;
  }

  if (action === "export-md") {
    event.preventDefault();
    exportBrief("md");
    return;
  }

  if (action === "export-json") {
    event.preventDefault();
    exportBrief("json");
  }
});

window.addEventListener("popstate", () => routeFromLocation());

routeFromLocation();
