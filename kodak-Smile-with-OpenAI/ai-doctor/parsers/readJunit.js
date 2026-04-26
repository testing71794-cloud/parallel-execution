import fs from "fs";
import { parseStringPromise } from "xml2js";

function asArray(v) {
  if (!v) return [];
  return Array.isArray(v) ? v : [v];
}

function pickFailure(tc) {
  // JUnit can have <failure> or <error>
  const f = tc.failure?.[0] || tc.error?.[0];
  if (!f) return null;
  const attrs = f.$ || {};
  const message = attrs.message || "";
  const text = typeof f === "string" ? f : (f._ || "");
  return {
    message: message || (text || "").trim().split("\n")[0] || "Failure",
    details: (text || "").trim(),
  };
}

/**
 * Parse JUnit XML and extract failed testcases.
 * Returns:
 *  - failedTests: [{ name, time, message, details }]
 *  - failuresCount
 *  - summaryText (human-readable)
 */
export async function parseJUnit(reportPath) {
  const xml = fs.readFileSync(reportPath, "utf-8");

  const json = await parseStringPromise(xml, {
    explicitArray: true,
    trim: true,
    mergeAttrs: false,
    attrkey: "$",
    charkey: "_",
  });

  const suites = [];

  if (json.testsuites?.testsuite) suites.push(...asArray(json.testsuites.testsuite));
  if (json.testsuite) suites.push(...asArray(json.testsuite));

  const failedTests = [];

  for (const suite of suites) {
    const tcs = asArray(suite.testcase);
    for (const tc of tcs) {
      const fail = pickFailure(tc);
      if (!fail) continue;
      const name = tc.$?.name || tc.$?.classname || "Unknown Test";
      const time = tc.$?.time ? Number(tc.$.time) : undefined;
      failedTests.push({
        name,
        time,
        message: fail.message,
        details: fail.details,
      });
    }
  }

  const summaryText = failedTests
    .map((t) => {
      const secs = typeof t.time === "number" && !Number.isNaN(t.time) ? `${t.time}s` : "?s";
      return `- ${t.name} (${secs}) (${t.message})`;
    })
    .join("\n");

  return {
    failedTests,
    failuresCount: failedTests.length,
    summaryText,
    rawXml: xml,
  };
}
