// pipeline.mjs (FULL COPY-PASTE)
// ✅ Keeps your existing logic intact (memory, enrichment, alternative prompt, auto-fix)
// ✅ NEW: per-flow AI analysis (separate JSON per failed test)
// ✅ FIXED: screenshot matching per flow (LATEST RUN ONLY + EXACT MATCH) so email attaches correct failed screen per flow
// ✅ Returns: resultsByFlow[] for per-flow email formatting

import { parseJUnit } from "./parsers/readJunit.js";
import { callOpenAI } from "./clients/openaiHttp.mjs";
import { callCursorAI } from "./clients/cursorApi.mjs";
import { generateFix } from "./fix/fixFlow.js";
import {
  analyzeEnrichedFailure,
  buildCursorReport,
} from "./analyzers/cursorAnalyzer.mjs";

// AI mode: CURSOR_API (Cloud Agents) > ATP rules > OpenAI/Ollama
const USE_CURSOR_AI = (process.env.USE_CURSOR_AI ?? "1") === "1";
const USE_CURSOR_API =
  !!(process.env.CURSOR_API_KEY && process.env.CURSOR_GITHUB_REPO);

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

/* ---------------- PATHS ---------------- */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ai-doctor/ folder
const aiDoctorDir = note(__dirname);

// project root = one level up from ai-doctor
const projectRoot = path.resolve(aiDoctorDir, "..");

// common paths
const testsDir = path.join(projectRoot, "tests");
const elementsLoadPath = findFirstExisting([
  path.join(projectRoot, "elements", "loadElements.yaml"),
  path.join(projectRoot, "elements", "loadElements.yml"),
  path.join(projectRoot, "tests", "elements", "loadElements.yaml"),
  path.join(projectRoot, "tests", "elements", "loadElements.yml"),
  path.join(testsDir, "elements", "loadElements.yaml"),
  path.join(testsDir, "elements", "loadElements.yml"),
]);

const artifactsDir = path.join(aiDoctorDir, "artifacts");
const memoryPath = path.join(artifactsDir, "memory.json");

ensureDir(artifactsDir);

/* ---------------- MAIN ---------------- */

export async function runPipeline(reportPath) {
  console.log("📂 Reading JUnit report:", reportPath);

  const junit = await parseJUnit(reportPath);

  // Print per-flow failures like Maestro, but controlled
  if (junit.failuresCount > 0) {
    console.log("❌ Failed Flows:");
    for (const t of junit.failedTests || []) {
      const secs =
        typeof t.time === "number" && !Number.isNaN(t.time) ? `${t.time}s` : "?s";
      console.log(`- ${t.name} (${secs}) (${t.message})`);
    }
  }

  // ✅ If no failures, SKIP AI completely
  if (!junit.failuresCount || junit.failuresCount === 0) {
    console.log("✅ No failures found. Skipping AI analysis.");
    return {
      rootCause: "",
      failureType: "none",
      suggestedFix: "N/A",
      retryRecommended: false,
      confidence: 1,
      failuresCount: 0,
      failedTests: [],
      patchGenerated: false,
      resultsByFlow: [],
    };
  }

  // ---- Load memory ----
  const memoryObj = loadMemory(memoryPath);

  // ---- Enrich each failed test with YAML + elements mapping + history ----
  const enrichedFailures = (junit.failedTests || []).map((t) =>
    enrichFailure(t, memoryObj)
  );

  // ✅ NEW: per-flow analysis results
  const resultsByFlow = [];

  const aiMode = USE_CURSOR_API
    ? "Cursor Cloud Agents API"
    : USE_CURSOR_AI
      ? "Cursor AI (ATP-based rules)"
      : "OpenAI/Ollama";
  console.log(`🤖 Running analysis: ${aiMode}`);

  // Per-flow screenshot limit (default 1)
  const perFlowShotLimit = Number(process.env.AI_SCREENSHOT_LIMIT_PER_FLOW || "1");

  for (const f of enrichedFailures) {
    const flowName = f.testName || "Unknown Flow";
    const flowKey = f.flowKey || "unknown";

    // ✅ Match screenshots for this flow only (latest run + exact match)
    const flowShots = findScreenshotsForFlow(artifactsDir, flowName, flowKey, perFlowShotLimit);

    console.log(`🧪 ${flowName}`);
    console.log(`🖼 Matched screenshots: ${flowShots.length}`);
    for (const p of flowShots) console.log("   -", p);

    let parsed;

    if (USE_CURSOR_API) {
      // Cursor Cloud Agents API (same as Ollama/OpenAI - full AI analysis)
      const perFlowPrompt = buildPromptForSingleFlow(junit, f);
      const imagesBase64 = flowShots.map((p) => fs.readFileSync(p).toString("base64"));
      try {
        parsed = await callCursorAI({ prompt: perFlowPrompt, images: imagesBase64 });
        parsed = ensureSchema(parsed);
        console.log("🧠 Cursor API Root Cause:", parsed.rootCause);
        console.log("🛠 Suggested Fix:", parsed.suggestedFix);
      } catch (e) {
        console.log("❌ Cursor API failed:", e?.message || e, "- falling back to ATP rules");
        parsed = analyzeEnrichedFailure({ ...f, screenshots: flowShots });
      }
    } else if (USE_CURSOR_AI) {
      // Cursor AI: ATP-based rule analysis (no external API)
      parsed = analyzeEnrichedFailure({ ...f, screenshots: flowShots });
      console.log("🧠 Cursor Root Cause:", parsed.rootCause);
      console.log("🛠 Suggested Fix:", parsed.suggestedFix);
    } else {
      // OpenAI/Ollama path (legacy)
      const imagesBase64 = flowShots.map((p) => fs.readFileSync(p).toString("base64"));
      const perFlowPrompt = buildPromptForSingleFlow(junit, f);

      let aiRawText = "";
      try {
        aiRawText = await callOpenAI({
          prompt: perFlowPrompt,
          images: imagesBase64,
        });
      } catch (e) {
        console.log("❌ OpenAI request failed (per-flow):", e?.message || e);
        aiRawText = "";
      }

      parsed = extractJSON(aiRawText, junit, [f]);

      const repeated = isRepeatedSuggestion(memoryObj, flowKey, f.signature, parsed.suggestedFix);
      if (repeated) {
        const altPrompt = buildAlternativePrompt(perFlowPrompt, parsed.suggestedFix);
        let altText = "";
        try {
          altText = await callOpenAI({ prompt: altPrompt, images: imagesBase64 });
        } catch {
          altText = "";
        }
        const altParsed = extractJSON(altText, junit, [f]);
        if (
          altParsed &&
          typeof altParsed.suggestedFix === "string" &&
          altParsed.suggestedFix.trim() &&
          altParsed.suggestedFix.trim() !== (parsed.suggestedFix || "").trim()
        ) {
          parsed = altParsed;
          confidence = normalizeConfidence(parsed?.confidence);
        }
      }

      console.log("🧠 AI Root Cause:", parsed.rootCause);
      console.log("🛠 Suggested Fix:", parsed.suggestedFix);
    }

    let confidence = normalizeConfidence(parsed?.confidence);

    // Store memory entry for this flow
    addMemoryEntry(memoryObj, flowKey, {
      signature: f.signature,
      date: new Date().toISOString(),
      rootCause: parsed.rootCause,
      suggestedFix: parsed.suggestedFix,
      confidence,
    });

    // Auto-fix per flow (optional) – allow for Cursor API & OpenAI
    let patch = null;
    const AUTO_FIX_THRESHOLD = Number(process.env.AUTO_FIX_THRESHOLD || "0.6");
    if ((USE_CURSOR_API || !USE_CURSOR_AI) && confidence >= AUTO_FIX_THRESHOLD) {
      try {
        patch = await generateFix({ ...parsed, confidence });
        console.log("🧩 Patch Generated:", !!patch);
      } catch (e) {
        console.log("⚠️ Auto-fix generation failed:", e?.message || e);
      }
    }

    const ensured = ensureSchema(parsed);

    resultsByFlow.push({
      flowKey: flowKey,
      flowName: flowName,
      time: f.testTime,
      failureMessage: f.testMessage || "",
      rootCause: ensured.rootCause,
      failureType: ensured.failureType,
      suggestedFix: ensured.suggestedFix,
      retryRecommended: Boolean(ensured.retryRecommended),
      confidence: normalizeConfidence(ensured.confidence),
      patchGenerated: !!patch,
      screenshots: flowShots,
    });
  }

  // Save memory once at end
  saveMemory(memoryPath, memoryObj);

  // Write Cursor-ready report when using Cursor (API or ATP) and there are failures
  if ((USE_CURSOR_AI || USE_CURSOR_API) && resultsByFlow.length > 0) {
    const resultForReport = {
      failuresCount: junit.failuresCount,
      retryRecommended: resultsByFlow.some((r) => r.retryRecommended),
      resultsByFlow,
    };
    const cursorReport = buildCursorReport(resultForReport);
    const cursorReportPath = path.join(artifactsDir, "cursor-report.md");
    fs.writeFileSync(cursorReportPath, cursorReport, "utf-8");
    console.log("📄 Cursor report saved:", cursorReportPath);
  }

  // Compute overall summary (use first flow as headline + aggregate)
  const overallRetry = resultsByFlow.some((r) => r.retryRecommended);
  const avgConfidence =
    resultsByFlow.length > 0
      ? resultsByFlow.reduce((a, r) => a + (r.confidence || 0), 0) / resultsByFlow.length
      : 0.35;

  const headline = resultsByFlow[0] || {};

  return {
    rootCause: headline.rootCause || "Per-flow analysis generated.",
    failureType: headline.failureType || "per_flow",
    suggestedFix:
      "See resultsByFlow for per-test suggestions.\n\n" +
      resultsByFlow
        .map(
          (r) =>
            `- ${r.flowName}: ${r.suggestedFix ? r.suggestedFix.split("\n")[0] : "N/A"}`
        )
        .join("\n"),
    retryRecommended: overallRetry,
    confidence: normalizeConfidence(avgConfidence),
    failuresCount: junit.failuresCount,
    failedTests: (junit.failedTests || []).map(({ name, time, message }) => ({
      name,
      time,
      message,
    })),
    patchGenerated: resultsByFlow.some((r) => r.patchGenerated),
    resultsByFlow, // ✅ NEW
  };
}

/* ---------------- ENRICHMENT ---------------- */

function enrichFailure(test, memoryObj) {
  const flowKey = getFlowKeyFromTestName(test.name); // "flow10"
  const signature = String(test.message || "").trim() || "unknown_failure";

  const flowFilePath = findFlowYamlFile(flowKey);
  const flowYaml = readTextSafe(flowFilePath, 30000);

  const elementsYaml = readTextSafe(elementsLoadPath, 30000);

  const flowHistory = getFlowHistory(memoryObj, flowKey);
  const lastSameSig = flowHistory.filter((h) => h.signature === signature).slice(0, 3);
  const lastAny = flowHistory.slice(0, 5);

  return {
    flowKey,
    signature,
    testName: test.name,
    testTime: test.time,
    testMessage: test.message,
    flowFilePath,
    flowYaml,
    elementsLoadPath: elementsLoadPath || "",
    elementsYaml,
    memorySameSignature: lastSameSig,
    memoryRecent: lastAny,
  };
}

function getFlowKeyFromTestName(name) {
  const s = String(name || "");
  const m = s.match(/flow\s*0*([0-9]+)/i);
  if (m?.[1]) return `flow${Number(m[1])}`;
  return "unknown";
}

function findFlowYamlFile(flowKey) {
  if (!flowKey || flowKey === "unknown") return "";
  if (!fs.existsSync(testsDir)) return "";

  const files = fs.readdirSync(testsDir);
  const wantYaml = `${flowKey}.yaml`.toLowerCase();
  const wantYml = `${flowKey}.yml`.toLowerCase();

  for (const f of files) {
    const low = f.toLowerCase();
    if (low === wantYaml || low === wantYml) return path.join(testsDir, f);
  }

  for (const f of files) {
    const low = f.toLowerCase();
    if ((low.endsWith(".yaml") || low.endsWith(".yml")) && low.includes(flowKey)) {
      return path.join(testsDir, f);
    }
  }

  return "";
}

/* ---------------- PROMPT ---------------- */

// NEW: prompt for a single flow (keeps your enrichment blocks)
function buildPromptForSingleFlow(junit, f) {
  const summary = junit.summaryText || "(no failures)";
  const xmlExcerpt = (junit.rawXml || "").slice(0, 15000);

  const memSame = (f.memorySameSignature || [])
    .map((m) => `- ${m.date}: ${m.suggestedFix} (conf=${m.confidence})`)
    .join("\n");

  const memRecent = (f.memoryRecent || [])
    .map((m) => `- ${m.date}: [${m.signature}] ${m.suggestedFix} (conf=${m.confidence})`)
    .join("\n");

  const block = `
---- FAILED FLOW ----
Test Name: ${f.testName}
Message: ${f.testMessage}
Flow Key: ${f.flowKey}
Signature: ${f.signature}

Flow YAML (${f.flowFilePath || "NOT FOUND"}):
${f.flowYaml || "(flow yaml not found)"}

Elements Mapping (${f.elementsLoadPath || "NOT FOUND"}):
${f.elementsYaml || "(elements/loadElements.yaml not found)"}

Memory (same signature - last 3):
${memSame || "(none)"}

Memory (recent - last 5):
${memRecent || "(none)"}
`;

  return `
You are a senior mobile automation debugging AI for the Kodak Smile app.

Return ONLY valid JSON. No extra text.

JSON format:
{
  "rootCause": "string",
  "failureType": "string",
  "suggestedFix": "string",
  "retryRecommended": boolean,
  "confidence": number
}

Rules:
- Use the provided Flow YAML and Elements Mapping to give actionable fixes.
- Do NOT repeat suggestions that appear in Memory for the same signature; propose a different next step if repeated.
- If assertion text is flaky, suggest stable selectors (id-based) + waits + conditional popups handling.
- If screenshots are provided, use them to infer the screen state and adjust suggestions.

Failed tests summary:
${summary}

JUnit excerpt (truncated):
${xmlExcerpt}

Context:
${block}
`.trim();
}

function buildAlternativePrompt(originalPrompt, repeatedFix) {
  return `
${originalPrompt}

IMPORTANT: Your previous suggestedFix was already tried or repeated:
"${repeatedFix}"

Now propose an ALTERNATIVE suggestedFix (different approach), still returning ONLY valid JSON.
`.trim();
}

/* ---------------- MEMORY ---------------- */

function loadMemory(filePath) {
  try {
    if (!fs.existsSync(filePath)) return { flows: {} };
    const raw = fs.readFileSync(filePath, "utf-8");
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== "object") return { flows: {} };
    if (!obj.flows || typeof obj.flows !== "object") obj.flows = {};
    return obj;
  } catch {
    return { flows: {} };
  }
}

function saveMemory(filePath, obj) {
  try {
    ensureDir(path.dirname(filePath));
    fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), "utf-8");
  } catch {
    // ignore
  }
}

function getFlowHistory(memoryObj, flowKey) {
  const list = memoryObj?.flows?.[flowKey];
  return Array.isArray(list) ? list : [];
}

function addMemoryEntry(memoryObj, flowKey, entry, maxPerFlow = 30) {
  if (!memoryObj.flows) memoryObj.flows = {};
  if (!Array.isArray(memoryObj.flows[flowKey])) memoryObj.flows[flowKey] = [];
  memoryObj.flows[flowKey].unshift(entry);
  memoryObj.flows[flowKey] = memoryObj.flows[flowKey].slice(0, maxPerFlow);
}

function isRepeatedSuggestion(memoryObj, flowKey, signature, suggestedFix) {
  const fix = (suggestedFix || "").trim();
  if (!fix) return false;
  const hist = getFlowHistory(memoryObj, flowKey);
  const sameSig = hist.filter((h) => h.signature === signature);
  return sameSig.some((h) => (h.suggestedFix || "").trim() === fix);
}

/* ---------------- SCREENSHOTS ---------------- */

// FIXED: match screenshots for a specific flow
// - searches ONLY latest run folder: artifacts/test-output/<latest>/
// - matches ONLY failed screenshots
// - matches exact flow name token "(<Flow Name>)" (preferred)
// - flowKey exact boundary match (so flow1 will NOT match flow11)
// - returns newest first, limited by `limit`
function findScreenshotsForFlow(artifactsDir, flowName, flowKey, limit = 1) {
  try {
    if (!fs.existsSync(artifactsDir)) return [];

    const testOutputRoot = path.join(artifactsDir, "test-output");
    if (!fs.existsSync(testOutputRoot)) return [];

    const runDirs = fs
      .readdirSync(testOutputRoot, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => path.join(testOutputRoot, e.name));

    if (!runDirs.length) return [];

    // Latest run folder by mtime
    runDirs.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
    const latestRunDir = runDirs[0];

    const flowNameStr = String(flowName || "").trim();
    const flowKeyStr = String(flowKey || "").trim().toLowerCase(); // "flow1"

    // Screenshot filenames include "(<flowName>)"
    const wantedFlowNameToken = flowNameStr ? `(${flowNameStr})` : "";

    // Exact flowKey boundary match: flow1 != flow11
    const flowKeyRegex = flowKeyStr
      ? new RegExp(`(^|[^a-z0-9])${flowKeyStr}([^a-z0-9]|$)`, "i")
      : null;

    const found = [];

    const walk = (d) => {
      const entries = fs.readdirSync(d, { withFileTypes: true });
      for (const e of entries) {
        const full = path.join(d, e.name);
        if (e.isDirectory()) walk(full);
        else if (/\.(png|jpg|jpeg)$/i.test(e.name)) {
          const n = e.name;

          // only failed screenshots
          if (!n.includes("screenshot-❌-")) continue;

          const hitByExactName = wantedFlowNameToken && n.includes(wantedFlowNameToken);
          const hitByExactKey = flowKeyRegex ? flowKeyRegex.test(n.toLowerCase()) : false;

          if (hitByExactName || hitByExactKey) {
            found.push(full);
          }
        }
      }
    };

    walk(latestRunDir);

    found.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
    return found.slice(0, Math.max(0, Number(limit) || 0));
  } catch {
    return [];
  }
}

/* ---------------- BASIC HELPERS ---------------- */

function normalizeConfidence(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return 0;
  if (n > 1) return Math.min(1, n / 100);
  return Math.min(1, n);
}

function extractJSON(aiRaw, junit, enrichedFailures) {
  if (typeof aiRaw === "string" && aiRaw.trim()) {
    const fromText = tryParseJsonFromText(aiRaw);
    if (fromText) return ensureSchema(fromText);
  }
  return buildFallbackSuggestion(junit, enrichedFailures);
}

function tryParseJsonFromText(text) {
  if (!text || typeof text !== "string") return null;

  // 1) direct JSON
  try {
    return JSON.parse(text);
  } catch {}

  // 2) brace-scan candidates
  const candidates = extractJsonObjectCandidates(text);
  for (const c of candidates) {
    try {
      return JSON.parse(c);
    } catch {}
  }

  // 3) fenced blocks
  const fencedBlocks = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)\s*```/gi)];
  for (const m of fencedBlocks) {
    const block = (m[1] || "").trim();
    if (!block) continue;
    try {
      return JSON.parse(block);
    } catch {}
  }

  return null;
}

function extractJsonObjectCandidates(text) {
  const out = [];
  let depth = 0;
  let start = -1;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (ch === "{") {
      if (depth === 0) start = i;
      depth++;
    } else if (ch === "}") {
      if (depth > 0) depth--;
      if (depth === 0 && start !== -1) {
        const candidate = text.slice(start, i + 1).trim();
        if (candidate.length > 20) out.push(candidate);
        start = -1;
      }
    }
  }

  out.sort((a, b) => b.length - a.length);
  return out;
}

function buildFallbackSuggestion(junit, enrichedFailures) {
  const first = (enrichedFailures || [])[0] || {};
  const msgRaw = String(first.testMessage || "");
  const msg = msgRaw.toLowerCase();
  const flowKey = first.flowKey || "unknown";

  let suggestedFix = "";

  if (msg.includes("assertion is false") && msg.includes("visible")) {
    suggestedFix =
      `Flow ${flowKey} is failing due to a flaky/state-dependent assert:\n` +
      `- Failure: ${msgRaw}\n\n` +
      `Fix steps:\n` +
      `1) Replace text assert with a stable selector (id) from loadElements.yaml.\n` +
      `2) Add conditional routing using runFlow/when for alternate states.\n` +
      `3) Add waits before assert: waitForAnimationToEnd + wait: 1500.\n` +
      `4) If printer connect: retry loop + handle pairing/permission popups.\n`;
  } else if (msg.includes("element not found") || msg.includes("id matching regex")) {
    suggestedFix =
      `Flow ${flowKey} is failing because an element was not found:\n` +
      `- Failure: ${msgRaw}\n\n` +
      `Fix steps:\n` +
      `1) Add assertVisible for expected screen title BEFORE tapping.\n` +
      `2) Wrap tap in runFlow/when visible and add a retry loop.\n` +
      `3) Use stable id selectors + scrollUntilVisible if list is long.\n`;
  } else {
    suggestedFix =
      `Flow ${flowKey} failed:\n` +
      `- Failure: ${msgRaw}\n\n` +
      `Fix steps:\n` +
      `1) Add waitForAnimationToEnd + wait: 1500 around the failing step.\n` +
      `2) Add conditional popup handling (Allow/OK/Pair) before/after the step.\n` +
      `3) Add a retry loop for flaky network/bluetooth actions.\n`;
  }

  return {
    rootCause: "AI output parse failure (model did not return valid JSON)",
    failureType: "ai_parse",
    suggestedFix,
    retryRecommended: true,
    confidence: 0.35,
  };
}

function ensureSchema(obj) {
  return {
    rootCause: typeof obj.rootCause === "string" ? obj.rootCause : "Unknown",
    failureType: typeof obj.failureType === "string" ? obj.failureType : "unknown",
    suggestedFix:
      typeof obj.suggestedFix === "string" ? obj.suggestedFix : "Manual debugging required",
    retryRecommended: Boolean(obj.retryRecommended),
    confidence: obj.confidence ?? 0,
  };
}

function ensureDir(p) {
  try {
    if (!p) return;
    if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
  } catch {}
}

function findFirstExisting(paths) {
  for (const p of paths) {
    if (p && fs.existsSync(p)) return p;
  }
  return "";
}

function readTextSafe(filePath, maxChars = 20000) {
  try {
    if (!filePath || !fs.existsSync(filePath)) return "";
    const raw = fs.readFileSync(filePath, "utf-8");
    return raw.length > maxChars ? raw.slice(0, maxChars) + "\n...<truncated>" : raw;
  } catch {
    return "";
  }
}

function note(x) {
  return x;
}