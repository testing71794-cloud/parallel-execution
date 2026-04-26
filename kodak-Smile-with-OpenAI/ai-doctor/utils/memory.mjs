import fs from "fs";
import path from "path";

export function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

export function readJsonSafe(filePath, fallback = {}) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writeJsonSafe(filePath, obj) {
  const dir = path.dirname(filePath);
  ensureDir(dir);
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), "utf-8");
}

/**
 * Memory format:
 * {
 *   flows: {
 *     "flow10": [
 *       {
 *         signature: "Assertion is false: ...",
 *         date: "2026-02-17T...",
 *         rootCause: "...",
 *         suggestedFix: "...",
 *         confidence: 0.7
 *       }
 *     ]
 *   }
 * }
 */
export function loadMemory(memoryPath) {
  return readJsonSafe(memoryPath, { flows: {} });
}

export function getFlowHistory(memoryObj, flowKey) {
  const list = memoryObj?.flows?.[flowKey];
  return Array.isArray(list) ? list : [];
}

export function addFlowMemory(memoryObj, flowKey, entry, maxPerFlow = 30) {
  if (!memoryObj.flows) memoryObj.flows = {};
  if (!Array.isArray(memoryObj.flows[flowKey])) memoryObj.flows[flowKey] = [];

  memoryObj.flows[flowKey].unshift(entry); // newest first

  // keep only last N
  memoryObj.flows[flowKey] = memoryObj.flows[flowKey].slice(0, maxPerFlow);
  return memoryObj;
}

export function findRepeatedSuggestion(flowHistory, signature, suggestedFix) {
  const sameSig = flowHistory.filter((h) => h.signature === signature);
  return sameSig.some((h) => (h.suggestedFix || "").trim() === (suggestedFix || "").trim());
}