import { execSync } from "child_process";
import os from "os";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

/* ---------------- PATH HELPERS ---------------- */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ai-doctor/utils -> ai-doctor -> project root
const projectRoot = path.resolve(__dirname, "..", "..");

// actual maestro tests folder
const testsDir =
  process.env.MAESTRO_TEST_DIR ||
  path.join(projectRoot, "tests");

/* ---------------- MAESTRO PATH ---------------- */

function getMaestroCmd() {
  // 1) If MAESTRO_PATH env provided
  if (process.env.MAESTRO_PATH && fs.existsSync(process.env.MAESTRO_PATH)) {
    return process.env.MAESTRO_PATH;
  }

  // 2) ~/.maestro/bin/maestro
  const home = os.homedir();
  const p = path.join(home, ".maestro", "bin", "maestro");
  if (fs.existsSync(p)) return p;

  // 3) fallback
  return "maestro";
}

/* ---------------- RETRY ---------------- */

export async function retryTest() {
  const maestro = getMaestroCmd();

  if (!fs.existsSync(testsDir)) {
    console.error("❌ Retry aborted: tests directory not found:");
    console.error(testsDir);
    return false; // prevent crash
  }

  const cmd = `${maestro} test "${testsDir}"`;

  console.log("🔁 Retrying with:", cmd);

  try {
    execSync(cmd, {
      stdio: "inherit",
      shell: true,
    });
    return true;
  } catch (err) {
    console.error("❌ Retry failed:", err.message);
    return false; // don't crash AI agent
  }
}