import { execSync } from "child_process";
execSync("maestro test flows --format junit --output report.xml",{stdio:"inherit"});
