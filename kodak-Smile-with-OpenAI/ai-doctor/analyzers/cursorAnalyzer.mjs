/**
 * Cursor AI Analyzer – ATP-based failure analysis (no Ollama/OpenAI)
 * Uses docs/ATP_KNOWLEDGE_BASE.md + https://docs.maestro.dev for suggestions.
 * Produces reports optimized for Cursor Chat analysis.
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const projectRoot = path.resolve(__dirname, "..", "..");
const atpPath = path.join(projectRoot, "docs", "ATP_KNOWLEDGE_BASE.md");

// ATP-based fix patterns (from knowledge base)
const FIX_PATTERNS = [
  {
    match: /imageRelativelayout|imageRelative/i,
    fix: `Element id: imageRelativelayout not found in app.
Fix: Replace with coordinate tap: tapOn: { point: "20%,30%" }
See docs/ATP_KNOWLEDGE_BASE.md – avoid imageRelativelayout.`,
    type: "selectors",
    confidence: 0.9,
  },
  {
    match: /assertion is false.*visible|"KODAK SMILE" is visible/i,
    fix: `Flaky/state-dependent assert – home screen not reached.
Fix steps:
1) Add waitForAnimationToEnd + wait: 1500 before assertVisible.
2) Add conditional popup handling (Allow/OK/Pair) before home assert.
3) Use runFlow/when for alternate states (Rate App, Fine-Tune, etc).
4) Ensure output.home.titleText = "KODAK SMILE" in elements/home.js.`,
    type: "timing",
    confidence: 0.85,
  },
  {
    match: /element not found|id matching regex/i,
    fix: `Element not found – selector may be wrong or element not yet visible.
Fix steps:
1) Add assertVisible for expected screen title BEFORE tapping.
2) Wrap tap in runFlow/when visible and add retry loop.
3) Prefer text or point: over id: when id is unknown (see ATP knowledge base).
4) Use scrollUntilVisible if element is in a scrollable list.`,
    type: "selectors",
    confidence: 0.8,
  },
  {
    match: /imageViewPreview|imageRelativelayout/i,
    fix: `Preview/thumbnail element not found.
Fix: Use point: "20%,30%" for photo grid, or verify element id in app hierarchy.`,
    type: "selectors",
    confidence: 0.85,
  },
  {
    match: /Text matching regex: Text/i,
    fix: `Selector "Text" is too ambiguous – matches many elements.
Fix: Use more specific text (e.g. "Add Text") or id: if available.
See ED_12 in ATP – tapOn Text for add text tool.`,
    type: "selectors",
    confidence: 0.9,
  },
  {
    match: /print|printing|printer/i,
    fix: `Print-related failure.
Fix: Ensure printer connected, paper loaded. Add waitForPrinting flow.
Handle: Print Successful, Cool down, Pair dialogs. See PR_* in ATP.`,
    type: "printing",
    confidence: 0.7,
  },
  {
    match: /connect|bluetooth|pairing/i,
    fix: `Connection-related failure.
Fix: Add retry loop for Search Again + Connect. Handle Bluetooth pairing popup.
See CO_*, ON_03 in ATP – Find My Printer → Allow → Connect.`,
    type: "bluetooth",
    confidence: 0.75,
  },
  {
    match: /permission|allow|denied/i,
    fix: `Permission dialog not handled.
Fix: Add runFlow/when visible: "Allow" or "While using the app" before step.
See ATP – native dialogs vary by device.`,
    type: "permissions",
    confidence: 0.85,
  },
];

function getFlowKeyFromTestName(name) {
  const s = String(name || "");
  const m = s.match(/flow\s*0*([0-9]+)/i);
  if (m?.[1]) return `flow${Number(m[1])}`;
  return "unknown";
}

function analyzeFailure(testName, testMessage, flowYaml = "", flowKey = "") {
  const msg = String(testMessage || "").trim();
  const key = flowKey || getFlowKeyFromTestName(testName);

  for (const p of FIX_PATTERNS) {
    if (p.match.test(msg)) {
      return {
        rootCause: `ATP pattern match: ${p.type}`,
        failureType: p.type,
        suggestedFix: p.fix,
        retryRecommended: true,
        confidence: p.confidence,
      };
    }
  }

  // Default fallback
  return {
    rootCause: "Unclassified failure – review with Cursor AI",
    failureType: "other",
    suggestedFix: `Flow ${key} failed: ${msg}

Fix steps (from ATP knowledge base):
1) Add waitForAnimationToEnd + wait: 1500 around failing step.
2) Add conditional popup handling (Allow/OK/Pair).
3) Use docs/ATP_KNOWLEDGE_BASE.md for element text and Maestro mapping.
4) Paste this report into Cursor Chat for deeper analysis.`,
    retryRecommended: true,
    confidence: 0.5,
  };
}

/**
 * Analyze enriched failure (pipeline format)
 */
export function analyzeEnrichedFailure(f) {
  return analyzeFailure(
    f.testName,
    f.testMessage,
    f.flowYaml,
    f.flowKey
  );
}

/**
 * Batch analyze failures – returns resultsByFlow format
 */
export function analyzeFailures(enrichedFailures) {
  return enrichedFailures.map((f) => {
    const analyzed = analyzeEnrichedFailure(f);
    return {
      flowKey: f.flowKey || "unknown",
      flowName: f.testName || "Unknown",
      time: f.testTime,
      failureMessage: f.testMessage || "",
      rootCause: analyzed.rootCause,
      failureType: analyzed.failureType,
      suggestedFix: analyzed.suggestedFix,
      retryRecommended: analyzed.retryRecommended,
      confidence: analyzed.confidence,
      patchGenerated: false,
      screenshots: f.screenshots || [],
    };
  });
}

/**
 * Build Cursor-ready markdown report for pasting into Cursor Chat
 */
export function buildCursorReport(result) {
  const lines = [
    "# Kodak Smile Maestro Failure Report",
    "",
    "**Analyzed with ATP knowledge base (no external LLM).**",
    "",
    "## Summary",
    `- Failures: ${result.failuresCount || 0}`,
    `- Retry recommended: ${result.retryRecommended ? "Yes" : "No"}`,
    "",
    "## Per-flow analysis",
    "",
  ];

  for (const r of result.resultsByFlow || []) {
    lines.push(`### ${r.flowName}`);
    lines.push(`- **Failure:** ${r.failureMessage}`);
    lines.push(`- **Root cause:** ${r.rootCause}`);
    lines.push(`- **Suggested fix:**`);
    lines.push("```");
    lines.push(r.suggestedFix || "N/A");
    lines.push("```");
    lines.push(`- **Confidence:** ${r.confidence ?? "N/A"}`);
    lines.push("");
  }

  lines.push("## Next steps");
  lines.push("1. Apply suggested fixes from docs/ATP_KNOWLEDGE_BASE.md");
  lines.push("2. Run `./doctor.sh` or `npm run doctor` to re-test");
  lines.push("3. For deeper analysis, share flow YAML + screenshot in Cursor Chat");
  lines.push("");

  return lines.join("\n");
}

/**
 * Load ATP knowledge base excerpt (for context in reports)
 */
export function getAtpExcerpt() {
  try {
    if (fs.existsSync(atpPath)) {
      return fs.readFileSync(atpPath, "utf-8").slice(0, 3000);
    }
  } catch {}
  return "(ATP knowledge base not found)";
}
