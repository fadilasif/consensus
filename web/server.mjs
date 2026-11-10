#!/usr/bin/env node
/**
 * Consensus local web bridge.
 *
 * This process is intentionally thin. It serves the frontend, exposes the
 * existing artifacts as read-only JSON, and invokes the unchanged Python CLI
 * for new analyses. It does not contain analysis, classification, or reporting
 * logic of its own.
 */

import { createReadStream, existsSync } from "node:fs";
import { readFile, realpath, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const PUBLIC_DIR = path.join(HERE, "public");
const PUBLIC_REAL_DIR = await realpath(PUBLIC_DIR);
const DATA_DIR = process.env.CONSENSUS_DATA_DIR
  ? path.resolve(process.env.CONSENSUS_DATA_DIR)
  : path.join(ROOT, "data");

const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 4173);
const MAX_BODY_BYTES = 1_000_000;
const MAX_QUESTION_LENGTH = 500;
const ANALYSIS_TIMEOUT_MS = 45 * 60 * 1000;
const HEARTBEAT_MS = 15_000;

const VENV_PYTHON = path.join(ROOT, ".venv", "bin", "python");
const PYTHON =
  process.env.CONSENSUS_PYTHON || (existsSync(VENV_PYTHON) ? VENV_PYTHON : "python3");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2",
};

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
};

const CATEGORY_LABELS = {
  IRRELEVANT: "Irrelevant",
};

function log(...parts) {
  const stamp = new Date().toISOString().slice(11, 19);
  console.log(`[${stamp}]`, ...parts);
}

function normaliseQuestion(value) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, "")
    .replace(/[\r\n]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function questionKey(question) {
  return createHash("sha256")
    .update(normaliseQuestion(question), "utf8")
    .digest("hex")
    .slice(0, 16);
}

function normaliseUrlInput(input) {
  let raw = String(input || "").trim();

  if (!raw) return null;

  if (/^[A-Za-z0-9_-]{11}$/.test(raw)) {
    return {
      videoId: raw,
      url: `https://www.youtube.com/watch?v=${raw}`,
    };
  }

  if (!/^https?:\/\//i.test(raw)) {
    raw = `https://${raw}`;
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }

  let host = parsed.hostname.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);

  let videoId = null;

  if (
    ["youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"].includes(host)
  ) {
    if (parsed.pathname === "/watch") {
      videoId = parsed.searchParams.get("v");
    } else if (/^\/(shorts|embed|live)\//.test(parsed.pathname)) {
      videoId = parsed.pathname.split("/").filter(Boolean)[1] || null;
    }
  } else if (host === "youtu.be") {
    videoId = parsed.pathname.split("/").filter(Boolean)[0] || null;
  }

  if (!videoId || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) {
    return null;
  }

  return {
    videoId,
    url: parsed.toString(),
  };
}

function humanizeCategory(name) {
  if (CATEGORY_LABELS[name]) return CATEGORY_LABELS[name];

  return String(name || "")
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((word, index) => (index === 0 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function cleanComment(value) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function redact(value) {
  return String(value || "")
    .replace(/\b(key|api_key|apikey|token|authorization)\s*=\s*[^&\s]+/gi, "$1=***")
    .replace(/\bBearer\s+[A-Za-z0-9._-]+/gi, "Bearer ***");
}

async function readJson(filePath) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

function numberOrNull(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function buildDistribution(aggregation) {
  const distribution = aggregation?.classification_distribution;

  if (!distribution || typeof distribution !== "object") return [];

  const descriptions = new Map(
    (Array.isArray(aggregation?.categories) ? aggregation.categories : [])
      .filter((category) => category && typeof category === "object")
      .map((category) => [category.name, category.description]),
  );

  return Object.entries(distribution)
    .filter(([, value]) => value && typeof value === "object")
    .map(([key, value]) => ({
      key,
      label: humanizeCategory(key),
      count: numberOrNull(value.count) ?? 0,
      percentage: numberOrNull(value.percentage) ?? 0,
      description:
        descriptions.get(key) ||
        (key === "IRRELEVANT" ? "Not about the research question." : ""),
    }));
}

function buildTopComments(analysis, processed, snapshot) {
  const source = Array.isArray(snapshot)
    ? snapshot
    : Array.isArray(analysis?.comments?.top_comments) && analysis.comments.top_comments.length
      ? analysis.comments.top_comments
      : Array.isArray(processed?.comments)
        ? processed.comments
        : [];

  return source
    .filter((comment) => comment && typeof comment === "object")
    .map((comment) => ({
      comment: cleanComment(comment.comment),
      likes: numberOrNull(comment.likes) ?? 0,
    }))
    .filter((comment) => comment.comment)
    .sort((a, b) => b.likes - a.likes)
    .slice(0, 10);
}

function videoMetrics(analysis, processed, aggregation, snapshot) {
  const analysisVideo = analysis?.video || {};
  const processedVideo = processed?.video || {};
  const snapshotVideo = snapshot && typeof snapshot === "object" ? snapshot : {};

  return {
    title:
      String(
        snapshotVideo.title ||
          analysisVideo.title ||
          processedVideo.title ||
          "",
      ).trim() || "Untitled YouTube video",
    views: numberOrNull(
      snapshotVideo.views ?? analysisVideo.views ?? processedVideo.views,
    ),
    likes: numberOrNull(
      snapshotVideo.likes ?? analysisVideo.video_likes ?? processedVideo.likes,
    ),
    comments:
      numberOrNull(snapshotVideo.comments) ??
      numberOrNull(aggregation?.total_top_level_comments) ??
      numberOrNull(analysisVideo.total_comments) ??
      numberOrNull(analysis?.comments?.total_comments) ??
      (Array.isArray(processed?.comments) ? processed.comments.length : null),
    replies:
      numberOrNull(snapshotVideo.replies) ??
      numberOrNull(aggregation?.total_replies_in_video) ??
      numberOrNull(analysisVideo.total_replies) ??
      numberOrNull(analysis?.replies?.total_replies),
  };
}

async function loadBrief(videoId, key) {
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId) || !/^[a-f0-9]{16}$/.test(key)) {
    return null;
  }

  const prefix = `${videoId}_${key}`;
  const classifications = path.join(DATA_DIR, "classifications");
  const report = await readJson(path.join(classifications, `${prefix}_report.json`));

  if (!report || typeof report !== "object" || typeof report.report !== "string") {
    return null;
  }

  const metadata = await readJson(
    path.join(classifications, `${prefix}_run_metadata.json`),
  );
  const reportSignature = String(report.run_signature || "");
  const metadataSignature =
    metadata && typeof metadata === "object"
      ? String(metadata.run_signature || "")
      : "";

  // Show a report only when it belongs to the current classification.
  // Otherwise an older narrative could be paired with newer aggregation and
  // comments.
  if (!reportSignature || reportSignature !== metadataSignature) {
    return null;
  }

  const aggregation = await readJson(path.join(classifications, `${prefix}_aggregation.json`));
  const analysis = await readJson(path.join(DATA_DIR, "analysis", `${videoId}.json`));
  const processed = await readJson(path.join(DATA_DIR, "processed", `${videoId}.json`));

  const question = String(
    report.user_question || report.research_question || "",
  ).trim();

  const classified =
    numberOrNull(aggregation?.total_comments_classified) ??
    numberOrNull(analysis?.comments?.total_comments) ??
    (Array.isArray(processed?.comments) ? processed.comments.length : 0);

  const irrelevant =
    numberOrNull(aggregation?.irrelevant_comments) ??
    numberOrNull(aggregation?.classification_distribution?.IRRELEVANT?.count) ??
    0;

  const relevant =
    numberOrNull(aggregation?.relevant_comments) ?? Math.max(0, classified - irrelevant);

  const snapshotVideo =
    report.video && typeof report.video === "object" ? report.video : {};
  const snapshotComments = Array.isArray(report.top_comments)
    ? report.top_comments
    : null;

  const video = videoMetrics(analysis, processed, aggregation, snapshotVideo);

  return {
    videoId,
    questionKey: key,
    question,
    video: {
      ...video,
      url: `https://www.youtube.com/watch?v=${videoId}`,
    },
    report: {
      text: report.report,
      generatedAt: String(report.generated_at || ""),
      model: String(report.model || ""),
      reasoning: String(report.reasoning_effort || ""),
    },
    questionInterpretation: String(aggregation?.question_interpretation || "").trim(),
    distribution: buildDistribution(aggregation),
    relevance: {
      classified,
      relevant,
      irrelevant,
      relevantPercentage: classified ? (relevant / classified) * 100 : 0,
      irrelevantPercentage: classified ? (irrelevant / classified) * 100 : 0,
    },
    topComments: buildTopComments(analysis, processed, snapshotComments),
    scope: {
      classificationPopulation: String(aggregation?.classification_population || ""),
      totalTopLevelComments: numberOrNull(aggregation?.total_top_level_comments),
      totalReplies: numberOrNull(aggregation?.total_replies_in_video),
    },
  };
}

function jsonResponse(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    ...SECURITY_HEADERS,
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function textResponse(res, status, message) {
  const body = `${message}\n`;
  res.writeHead(status, {
    ...SECURITY_HEADERS,
    "Content-Type": "text/plain; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

async function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];

    req.on("data", (chunk) => {
      size += chunk.length;

      if (size > MAX_BODY_BYTES) {
        reject(new Error("Request is too large."));
        req.destroy();
        return;
      }

      chunks.push(chunk);
    });

    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        reject(new Error("Request body must be valid JSON."));
      }
    });

    req.on("error", reject);
  });
}

function analysisError(message, hint) {
  return { type: "error", message, hint: hint || "" };
}

function friendlyError(message, stderr) {
  const combined = `${message}\n${stderr}`.toLowerCase();

  if (combined.includes("no module named consensus") || combined.includes("modulenotfounderror")) {
    return {
      message: "The Consensus Python package is not available.",
      hint: "From the project root, run `uv sync`, then try again.",
    };
  }

  if (
    combined.includes("youtube_api_key") ||
    combined.includes("subq_api_key") ||
    combined.includes("groq_api_key") ||
    combined.includes("api key")
  ) {
    return {
      message: "A required API key is missing.",
      hint: "Check the .env file in the project root, then try again.",
    };
  }

  if (combined.includes("video not found")) {
    return {
      message: "That video could not be found.",
      hint: "Check that the link is public and still available.",
    };
  }

  if (combined.includes("invalid youtube")) {
    return {
      message: "That YouTube link is not valid.",
      hint: "Paste a watch, share, Shorts, or live link.",
    };
  }

  return {
    message: message || "The analysis stopped before it could finish.",
    hint: "Check the video link and your API keys, then try again.",
  };
}

async function handleAnalyze(req, res) {
  let body;

  try {
    body = await readBody(req);
  } catch (error) {
    jsonResponse(res, 400, { error: error.message });
    return;
  }

  const parsed = normaliseUrlInput(body?.url);
  const question = normaliseQuestion(body?.question);

  res.writeHead(200, {
    ...SECURITY_HEADERS,
    "Content-Type": "application/x-ndjson; charset=utf-8",
    "Cache-Control": "no-store, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  });

  let finished = false;
  let child = null;
  let heartbeat = null;
  let timeout = null;
  let buffer = "";
  let stderr = "";
  let errorEvent = null;

  const send = (event) => {
    if (finished || res.writableEnded) return;
    res.write(`${JSON.stringify(event)}\n`);
  };

  const finish = (event) => {
    if (finished) return;
    finished = true;

    if (heartbeat) clearInterval(heartbeat);
    if (timeout) clearTimeout(timeout);

    if (event && !res.writableEnded) {
      res.write(`${JSON.stringify(event)}\n`);
    }
    res.end();

    terminateChild(child);
  };

  const stage = (name) => {
    send({ type: "stage", stage: name });
  };

  let metaSent = false;

  const sendMeta = async () => {
    if (metaSent) return;

    const processed = await readJson(path.join(DATA_DIR, "processed", `${parsed.videoId}.json`));
    const analysis = await readJson(path.join(DATA_DIR, "analysis", `${parsed.videoId}.json`));

    if (!processed && !analysis) return;

    metaSent = true;
    send({
      type: "meta",
      video: videoMetrics(analysis, processed, null, null),
    });
  };

  const handleLine = (rawLine) => {
    const line = rawLine.trim();
    if (!line) return;

    const lower = line.toLowerCase();

    if (lower.includes("collecting data")) {
      stage("collecting");
    } else if (lower.includes("cleaning and analysing")) {
      stage("cleaning");
    } else if (lower.includes("classifying comments")) {
      stage("classifying");
      void sendMeta();
    } else if (lower.includes("generating report")) {
      stage("generating");
    } else if (lower.includes("report saved")) {
      stage("saved");
    } else if (lower.includes("error:")) {
      errorEvent = analysisError(line.replace(/^.*?error:\s*/i, ""));
    } else if (lower.includes("video not found")) {
      errorEvent = analysisError(
        "That video could not be found.",
        "Check that the link is public and still available.",
      );
    } else if (lower.includes("invalid youtube url")) {
      errorEvent = analysisError(
        "That YouTube link is not valid.",
        "Paste a watch, share, Shorts, or live link.",
      );
    } else if (lower.includes("research question cannot be empty")) {
      errorEvent = analysisError(
        "A research question is required.",
        "Add a short question before starting the analysis.",
      );
    }
  };

  res.on("close", () => {
    finished = true;

    if (heartbeat) clearInterval(heartbeat);
    if (timeout) clearTimeout(timeout);

    terminateChild(child);
  });

  if (!parsed) {
    finish(
      analysisError(
        "That does not look like a YouTube video link.",
        "Paste a watch, share, Shorts, or live link.",
      ),
    );
    return;
  }

  if (!question) {
    finish(analysisError("A research question is required."));
    return;
  }

  if (question.length > MAX_QUESTION_LENGTH) {
    finish(
      analysisError(
        "That research question is too long.",
        `Keep it under ${MAX_QUESTION_LENGTH} characters.`,
      ),
    );
    return;
  }

  send({ type: "started", videoId: parsed.videoId, question });

  heartbeat = setInterval(() => send({ type: "ping" }), HEARTBEAT_MS);

  timeout = setTimeout(() => {
    finish(
      analysisError(
        "The analysis timed out.",
        "The providers may be slow. Try again in a little while.",
      ),
    );
  }, ANALYSIS_TIMEOUT_MS);

  try {
    child = spawn(PYTHON, ["-u", "-m", "consensus.main"], {
      cwd: ROOT,
      env: {
        ...process.env,
        CONSENSUS_LOG_LEVEL: process.env.CONSENSUS_LOG_LEVEL || "WARNING",
        PYTHONUNBUFFERED: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    finish(
      analysisError(
        "The local Python runtime could not be started.",
        "Check that Python is installed and the project dependencies are available.",
      ),
    );
    log("spawn failed", redact(error.message));
    return;
  }

  child.on("error", (error) => {
    log("python process error", redact(error.message));
    finish(
      analysisError(
        "The local Python runtime could not be started.",
        "Check that Python is installed and the project dependencies are available.",
      ),
    );
  });

  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";

    for (const line of lines) handleLine(line);
  });

  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderr += chunk;

    if (stderr.length > 12_000) {
      stderr = stderr.slice(-12_000);
    }
  });

  child.on("close", async (code) => {
    if (buffer.trim()) handleLine(buffer);
    buffer = "";

    if (finished) return;

    if (errorEvent) {
      finish(errorEvent);
      return;
    }

    if (code !== 0) {
      const friendly = friendlyError("", stderr);
      log("analysis failed", redact(stderr.split(/\r?\n/).filter(Boolean).pop() || `exit ${code}`));
      finish(analysisError(friendly.message, friendly.hint));
      return;
    }

    try {
      const data = await loadBrief(parsed.videoId, questionKey(question));

      if (!data) {
        finish(
          analysisError(
            "The analysis finished but no report artifact was found.",
            "Check the data directory and try again.",
          ),
        );
        return;
      }

      finish({ type: "done", data });
    } catch (error) {
      log("result load failed", redact(error.message));
      finish(
        analysisError(
          "The report was generated but could not be read.",
          "Check the data directory and try again.",
        ),
      );
    }
  });

  child.stdin.setEncoding("utf8");
  child.stdin.write(`${parsed.url}\n${question}\n`);
  child.stdin.end();
}

function terminateChild(child) {
  if (!child || child.exitCode !== null) return;

  child.kill("SIGTERM");

  const killTimer = setTimeout(() => {
    if (child.exitCode === null) child.kill("SIGKILL");
  }, 5000);
  killTimer.unref?.();
}

async function serveStatic(req, res, pathname) {
  let decoded;

  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    textResponse(res, 400, "Bad request.");
    return;
  }

  const relative = decoded === "/" ? "index.html" : decoded.replace(/^\/+/, "");
  const filePath = path.resolve(PUBLIC_DIR, relative);

  if (filePath !== PUBLIC_DIR && !filePath.startsWith(`${PUBLIC_DIR}${path.sep}`)) {
    textResponse(res, 403, "Forbidden.");
    return;
  }

  let realFilePath;

  try {
    realFilePath = await realpath(filePath);
  } catch {
    textResponse(res, 404, "Not found.");
    return;
  }

  if (
    realFilePath !== PUBLIC_REAL_DIR &&
    !realFilePath.startsWith(`${PUBLIC_REAL_DIR}${path.sep}`)
  ) {
    textResponse(res, 403, "Forbidden.");
    return;
  }

  let fileStat;

  try {
    fileStat = await stat(realFilePath);
  } catch {
    textResponse(res, 404, "Not found.");
    return;
  }

  if (fileStat.isDirectory()) {
    textResponse(res, 404, "Not found.");
    return;
  }

  const extension = path.extname(realFilePath).toLowerCase();
  const contentType = MIME_TYPES[extension] || "application/octet-stream";

  res.writeHead(200, {
    ...SECURITY_HEADERS,
    "Content-Type": contentType,
    "Content-Length": fileStat.size,
    "Cache-Control": extension === ".html" ? "no-store" : "public, max-age=300",
  });

  if (req.method === "HEAD") {
    res.end();
    return;
  }

  createReadStream(realFilePath).pipe(res);
}

const server = createServer(async (req, res) => {
  const method = req.method || "GET";
  let url;

  try {
    url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  } catch {
    textResponse(res, 400, "Bad request.");
    return;
  }

  const pathname = url.pathname;

  try {
    if (pathname === "/api/health") {
      if (method !== "GET") return jsonResponse(res, 405, { error: "Method not allowed." });
      return jsonResponse(res, 200, {
        ok: true,
        dataDir: DATA_DIR,
        python: PYTHON,
      });
    }

    if (pathname.startsWith("/api/briefs/")) {
      if (method !== "GET") return jsonResponse(res, 405, { error: "Method not allowed." });

      const parts = pathname.split("/").filter(Boolean);
      if (parts.length !== 4) return jsonResponse(res, 404, { error: "Brief not found." });

      const brief = await loadBrief(parts[2], parts[3]);
      if (!brief) return jsonResponse(res, 404, { error: "Brief not found." });

      return jsonResponse(res, 200, { brief });
    }

    if (pathname === "/api/analyze") {
      if (method !== "POST") return jsonResponse(res, 405, { error: "Method not allowed." });
      return await handleAnalyze(req, res);
    }

    if (pathname.startsWith("/api/")) {
      return jsonResponse(res, 404, { error: "Not found." });
    }

    if (method !== "GET" && method !== "HEAD") {
      return textResponse(res, 405, "Method not allowed.");
    }

    return await serveStatic(req, res, pathname);
  } catch (error) {
    log("request failed", redact(error.stack || error.message));
    if (!res.headersSent) {
      jsonResponse(res, 500, { error: "Internal server error." });
    } else if (!res.writableEnded) {
      res.end();
    }
  }
});

server.listen(PORT, HOST, () => {
  log(`Consensus web running at http://${HOST}:${PORT}`);
  log(`data: ${DATA_DIR}`);
  log(`python: ${PYTHON}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
