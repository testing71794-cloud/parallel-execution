/**
 * Cursor Cloud Agents API client
 * Uses Cursor's AI to analyze failures (same role as Ollama/OpenAI).
 * Requires: CURSOR_API_KEY, CURSOR_GITHUB_REPO
 * Docs: https://cursor.com/docs/cloud-agent/api/overview
 */

import "dotenv/config";

const CURSOR_API = "https://api.cursor.com";
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_TIME_MS = 120000; // 2 min

function extractJsonFromText(text) {
  if (!text || typeof text !== "string") return null;
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) return null;
  try {
    return JSON.parse(m[0]);
  } catch {
    return null;
  }
}

async function cursorFetch(path, options = {}) {
  const apiKey = process.env.CURSOR_API_KEY;
  if (!apiKey) throw new Error("CURSOR_API_KEY is required");

  const url = `${CURSOR_API}${path}`;
  const auth = Buffer.from(`${apiKey}:`).toString("base64");

  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Basic ${auth}`,
      ...options.headers,
    },
  });

  const txt = await res.text();
  if (!res.ok) throw new Error(`Cursor API ${res.status}: ${txt}`);

  try {
    return txt ? JSON.parse(txt) : {};
  } catch {
    return {};
  }
}

/**
 * Launch a Cursor Cloud Agent to analyze a failure.
 * Returns parsed JSON: { rootCause, suggestedFix, retryRecommended, confidence }
 */
export async function callCursorAI({ prompt, images = [], timeoutMs = MAX_POLL_TIME_MS }) {
  const repo = process.env.CURSOR_GITHUB_REPO;
  if (!repo) {
    throw new Error(
      "CURSOR_GITHUB_REPO required (e.g. https://github.com/user/repo). Set in .env"
    );
  }

  const promptText = `${prompt}

IMPORTANT: Do NOT modify any files or create branches. Only respond in this conversation with your analysis as valid JSON.
Return ONLY a JSON object: {"rootCause":"string","failureType":"string","suggestedFix":"string","retryRecommended":boolean,"confidence":number}`;

  const body = {
    prompt: {
      text: promptText,
      images: images.slice(0, 5).map((b64) => ({
        data: b64,
        dimension: { width: 1024, height: 768 },
      })),
    },
    source: {
      repository: repo.replace(/\/$/, ""),
      ref: process.env.CURSOR_GITHUB_REF || "main",
    },
    target: { autoCreatePr: false },
  };

  if (images.length === 0) delete body.prompt.images;

  console.log("🤖 Cursor Cloud Agent: launching...");
  const created = await cursorFetch("/v0/agents", {
    method: "POST",
    body: JSON.stringify(body),
  });

  const agentId = created?.id;
  if (!agentId) throw new Error("Cursor API: no agent id returned");

  const start = Date.now();
  let status = created?.status || "CREATING";

  while (status !== "FINISHED" && status !== "FAILED" && Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    const agent = await cursorFetch(`/v0/agents/${agentId}`);
    status = agent?.status || status;
    if (status === "FAILED") {
      throw new Error(`Cursor agent failed: ${agent?.summary || "unknown"}`);
    }
  }

  if (status !== "FINISHED") {
    throw new Error(`Cursor agent timeout (${timeoutMs}ms), status: ${status}`);
  }

  const conv = await cursorFetch(`/v0/agents/${agentId}/conversation`);
  const messages = conv?.messages || [];

  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.type === "assistant_message" && m?.text) {
      const json = extractJsonFromText(m.text);
      if (json) return json;
    }
  }

  throw new Error("Cursor agent did not return valid JSON");
}
