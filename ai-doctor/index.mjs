// index.mjs (FULL COPY-PASTE with MEMORY support)
//
// ✅ Adds persistent memory: ai-doctor/memory.json
// ✅ Loads memory at startup
// ✅ Writes/updates memory after runPipeline()
// ✅ Keeps your existing logic intact (tests, ai-report, email, retry, webhook)

import path from "path";
import fs from "fs";
import os from "os";
import "dotenv/config";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";

import { runPipeline } from "./pipeline.mjs";
import { triggerWebhook } from "./utils/webhook.mjs";
import { sendFailureEmail, isEmailConfigured } from "./utils/email.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Project root = parent folder of ai-doctor
const projectRoot = path.join(__dirname, "..");

// Report path
const reportPath = process.argv[2] || path.join(projectRoot, "report.xml");

const artifactDir = path.join(__dirname, "artifacts");
if (!fs.existsSync(artifactDir)) {
  fs.mkdirSync(artifactDir, { recursive: true });
}

console.log("🧠 Kodak Maestro AI Debug Agent Started");
console.log("📂 Using report:", reportPath);

function getMaestroCmd() {
  const p = path.join(os.homedir(), ".maestro", "bin", "maestro");
  return fs.existsSync(p) ? p : "maestro";
}

// ======================================================
// ✅ MEMORY (PERSIST ACROSS RUNS)
// ======================================================
const memoryPath = path.join(__dirname, "memory.json");

function safeReadJson(filePath, fallback = {}) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf-8").trim();
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function safeWriteJson(filePath, obj) {
  try {
    fs.writeFileSync(filePath, JSON.stringify(obj, null, 2));
    return true;
  } catch {
    return false;
  }
}

// Load memory (creates file later if missing)
let memory = safeReadJson(memoryPath, {});
console.log("🧾 Memory loaded:", memoryPath, `(keys=${Object.keys(memory).length})`);

// ======================================================
// RUN TESTS FROM /tests WITH LIVE FLOW UPDATES
// ======================================================
const testsDir = path.join(projectRoot, "tests");

if (!fs.existsSync(testsDir)) {
  console.error(`❌ Tests folder not found: ${testsDir}`);
  process.exit(2);
}

console.log("▶ Running fresh Maestro tests (ALL flows):", testsDir);

const stdoutLog = path.join(artifactDir, "maestro_stdout.log");
const stderrLog = path.join(artifactDir, "maestro_stderr.log");
const testOutputDir = path.join(artifactDir, "test-output");

// Always remove old report before running (prevents stale parsing)
try {
  if (fs.existsSync(reportPath)) fs.unlinkSync(reportPath);
} catch {}

// Ensure test output dir exists
try {
  if (!fs.existsSync(testOutputDir)) fs.mkdirSync(testOutputDir, { recursive: true });
} catch {}

// Run ALL flows (yaml + yml)
const maestroCmd = `${getMaestroCmd()} test "${testsDir}"/flow*.y*ml --format junit --output "${reportPath}" --test-output-dir "${testOutputDir}"`;

// LIVE OUTPUT + SAVE LOGS
const run = spawnSync(
  "bash",
  ["-lc", `${maestroCmd} 2> "${stderrLog}" | tee "${stdoutLog}"`],
  { cwd: projectRoot, stdio: "inherit" }
);

if (run.status === 0) {
  console.log("✅ Maestro command finished. report.xml generated (check results below).");
} else {
  console.log("❌ Maestro command failed (non-zero exit). Still attempting to analyze report…");
}

// Ensure report exists
if (!fs.existsSync(reportPath)) {
  console.error("❌ report.xml was not generated.");
  console.error("👉 Check logs:");
  console.error(" -", stdoutLog);
  console.error(" -", stderrLog);
  process.exit(2);
}

// ======================================================
// AI Analysis (per-flow + screenshot matching)
// ======================================================
const result = await runPipeline(reportPath);

const outFile = path.join(artifactDir, "ai-report.json");
fs.writeFileSync(outFile, JSON.stringify(result, null, 2));
console.log("📝 AI report saved:", outFile);

// ======================================================
// ✅ UPDATE MEMORY AFTER EACH RUN
// Stores last failure + fix suggestion per flowKey
// ======================================================
try {
  const now = new Date().toISOString();

  for (const r of result.resultsByFlow || []) {
    // Only store when we have a stable key
    // (Your pipeline uses flowKey; can be "unknown" if test name has no FlowXX)
    if (!r.flowKey || r.flowKey === "unknown") continue;

    memory[r.flowKey] = {
      flowKey: r.flowKey,
      flowName: r.flowName,
      lastFailure: r.failureMessage || "",
      lastRootCause: r.rootCause || "",
      lastSuggestedFix: r.suggestedFix || "",
      confidence: r.confidence ?? null,
      failureType: r.failureType || "",
      updatedAt: now,
    };
  }

  const wrote = safeWriteJson(memoryPath, memory);
  console.log(wrote ? "💾 Memory updated:" : "⚠️ Memory write failed:", memoryPath);
} catch (e) {
  console.log("⚠️ Memory update skipped:", e?.message || e);
}

// Print failed flows cleanly
if (Array.isArray(result.failedTests) && result.failedTests.length > 0) {
  console.log("❌ Failed Flows:");
  for (const t of result.failedTests) {
    console.log(`- ${t.name}${t.time ? ` (${t.time}s)` : ""} (${t.message})`);
  }
}

// ======================================================
// EMAIL (HTML + inline screenshots + attachments)
// ======================================================
try {
  const hasFailures =
    (typeof result.failuresCount === "number" && result.failuresCount > 0) ||
    (Array.isArray(result.failedTests) && result.failedTests.length > 0);

  if (hasFailures) {
    if (isEmailConfigured()) {
      const subject = `[Kodak Smile] Maestro Failed - ${result.failuresCount || 0} failure(s)`;

      const safe = (s) =>
        String(s || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");

      // Text fallback
      const text = [
        "Kodak Smile Maestro run failed.",
        "",
        `Suite: ${testsDir}`,
        `Report: ${reportPath}`,
        `AI Report: ${outFile}`,
        `Test Output Dir: ${testOutputDir}`,
        "",
        "Per-flow results:",
        ...(result.resultsByFlow || []).flatMap((r) => [
          `- ${r.flowName} ${r.time ? `(${r.time}s)` : ""}`,
          `  Failure: ${r.failureMessage || ""}`,
          `  Root cause: ${r.rootCause || ""}`,
          `  Suggested fix: ${r.suggestedFix || ""}`,
          "",
        ]),
      ].join("\n");

      // Build attachments (inline images via CID + also attached)
      const attachments = [];
      for (const r of result.resultsByFlow || []) {
        const shots = Array.isArray(r.screenshots) ? r.screenshots : [];
        shots.forEach((p, idx) => {
          if (typeof p === "string" && fs.existsSync(p)) {
            attachments.push({
              filename: path.basename(p),
              path: p,
              cid: `${r.flowKey}_${idx}`, // allows inline display in HTML
            });
          }
        });
      }

      const perFlowHtml = (result.resultsByFlow || [])
        .map((r) => {
          const shots = Array.isArray(r.screenshots) ? r.screenshots : [];
          const imgs = shots
            .map(
              (_p, idx) =>
                `<div style="margin:8px 0;">
                   <img src="cid:${r.flowKey}_${idx}" style="max-width:520px;border:1px solid #ddd;border-radius:10px"/>
                 </div>`
            )
            .join("");

          return `
            <div style="padding:14px;border:1px solid #e5e5e5;border-radius:12px;margin:12px 0;">
              <div style="font-size:16px;font-weight:700;margin-bottom:6px;">
                ${safe(r.flowName)} ${
                  r.time ? `<span style="color:#666;font-weight:500">(${r.time}s)</span>` : ""
                }
              </div>
              <div style="color:#444;margin:6px 0;"><b>Failure:</b> ${safe(
                r.failureMessage
              )}</div>
              <div style="color:#444;margin:6px 0;"><b>Root cause:</b> ${safe(r.rootCause)}</div>
              <div style="color:#444;margin:6px 0;white-space:pre-wrap;"><b>Suggested fix:</b><br/>${safe(
                r.suggestedFix
              )}</div>
              ${
                imgs
                  ? `<div style="margin-top:10px"><b>Failed screen:</b>${imgs}</div>`
                  : ""
              }
              <div style="color:#777;margin-top:8px;"><b>Confidence:</b> ${
                r.confidence ?? "N/A"
              }</div>
            </div>
          `;
        })
        .join("");

      const html = `
        <div style="font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:auto;">
          <h2 style="margin:0 0 8px 0;">Kodak Smile Maestro run failed</h2>

          <div style="color:#555;margin-bottom:14px;">
            <div><b>Suite:</b> ${safe(testsDir)}</div>
            <div><b>Report:</b> ${safe(reportPath)}</div>
            <div><b>AI Report:</b> ${safe(outFile)}</div>
            <div><b>Test Output Dir:</b> ${safe(testOutputDir)}</div>
          </div>

          <div style="padding:12px;background:#f7f7f7;border:1px solid #eee;border-radius:12px;">
            <div><b>Failures:</b> ${safe(result.failuresCount)}</div>
            <div><b>Retry Recommended:</b> ${result.retryRecommended ? "Yes" : "No"}</div>
          </div>

          <h3 style="margin:18px 0 8px 0;">Per-flow AI suggestions</h3>
          ${perFlowHtml || "<div>No per-flow results produced.</div>"}
        </div>
      `;

      const info = await sendFailureEmail({ subject, text, html, attachments });

      console.log("📧 Email accepted by SMTP:", info.accepted);
      console.log("📧 Email messageId:", info.messageId);
      console.log("📧 Sent to:", process.env.FAIL_EMAIL_TO);
      console.log("🖼 Attachments:", attachments.length);
    } else {
      console.log("📧 Email not sent (SMTP env not configured).");
    }
  } else {
    console.log("📧 No failures detected (no email).");
  }
} catch (e) {
  console.error("❌ Email send failed:", e?.message || e);
}

// ======================================================
// Retry only failed flows
// ======================================================
if (result.retryRecommended) {
  console.log("🔁 Retry triggered by AI");

  const flowNums = [
    ...new Set(
      (result.failedTests || [])
        .map((t) => (String(t.name || "").match(/\bFlow(\d+)\b/i) || [])[1])
        .filter(Boolean)
    ),
  ].sort((a, b) => Number(a) - Number(b));

  if (flowNums.length === 0) {
    console.log("⚠️ Retry skipped: no Flow numbers found in failedTests.");
  } else {
    const retryFiles = [];
    for (const n of flowNums) {
      const f1 = path.join(testsDir, `flow${n}.yaml`);
      const f2 = path.join(testsDir, `flow${n}.yml`);
      if (fs.existsSync(f1)) retryFiles.push(f1);
      else if (fs.existsSync(f2)) retryFiles.push(f2);
      else console.log(`⚠️ Missing file for Flow${n}: expected flow${n}.yaml or flow${n}.yml`);
    }

    if (retryFiles.length === 0) {
      console.log("❌ Retry skipped: no failed flow YAML files found.");
    } else {
      console.log("🔁 Retrying ONLY failed flows:");
      for (const f of retryFiles) console.log(" -", f);

      const retryReportPath = path.join(projectRoot, "report_retry.xml");

      const retryCmd =
        `${getMaestroCmd()} test ${retryFiles.map((f) => `"${f}"`).join(" ")} ` +
        `--format junit --output "${retryReportPath}" --test-output-dir "${testOutputDir}"`;

      spawnSync("bash", ["-lc", `${retryCmd} 2>> "${stderrLog}" | tee -a "${stdoutLog}"`], {
        cwd: projectRoot,
        stdio: "inherit",
      });

      console.log("✅ Retry finished. Retry report:", retryReportPath);
    }
  }
}

await triggerWebhook(result);
console.log("✅ AI Debug Agent Completed");