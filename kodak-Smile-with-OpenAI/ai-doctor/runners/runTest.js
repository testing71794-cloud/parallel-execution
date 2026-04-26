import { execSync } from "child_process";
execSync("node index.mjs report.xml",{stdio:"inherit"});
