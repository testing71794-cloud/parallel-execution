// Call local editing server to run ADB toolbar helper (no GraalJS ProcessBuilder).
// Env: U2_SERIAL, U2_TOOL, U2_EXTRA (optional flags e.g. "--apply-swipe")
var serial =
  typeof U2_SERIAL !== "undefined" && U2_SERIAL
    ? U2_SERIAL
    : typeof DEVICE_ID !== "undefined" && DEVICE_ID
      ? DEVICE_ID
      : "ZA222RFQ75";
var tool = typeof U2_TOOL !== "undefined" && U2_TOOL ? U2_TOOL : "";
var extra = typeof U2_EXTRA !== "undefined" && U2_EXTRA ? U2_EXTRA : "--apply-swipe";

if (!tool && extra.indexOf("--cancel-save") < 0 && extra.indexOf("--ar") < 0) {
  throw new Error("U2_TOOL required (or use --ar / --cancel-save)");
}

var port =
  typeof EDITING_VERIFY_PORT !== "undefined" && EDITING_VERIFY_PORT
    ? EDITING_VERIFY_PORT
    : "8767";
var url = "http://127.0.0.1:" + port + "/tool/adb";

var response = http.post(url, {
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    serial: serial,
    tool: tool,
    extra: extra,
  }),
});

var bodyText = response.body || "";
var parsed = null;
try {
  parsed = json(bodyText);
} catch (ignore) {
  parsed = null;
}

if (response.status < 200 || response.status >= 300) {
  var err = parsed && parsed.error ? parsed.error : bodyText.substring(0, 500);
  throw new Error("adb tool HTTP " + response.status + ": " + err);
}

var ok = parsed && (parsed.ok === true || parsed.exit === 0);
output.u2_tool_ok = ok === true;
output.u2_tool_exit = parsed && typeof parsed.exit !== "undefined" ? parsed.exit : -1;
output.u2_tool_log = parsed && parsed.log ? String(parsed.log).substring(0, 2000) : bodyText.substring(0, 2000);
console.log("[u2] " + (output.u2_tool_log || "").split("\n").slice(0, 8).join(" | "));

if (!ok) {
  throw new Error(
    "adb tool failed exit=" +
      output.u2_tool_exit +
      " tool=" +
      tool +
      " log=" +
      String(output.u2_tool_log).substring(0, 500)
  );
}
