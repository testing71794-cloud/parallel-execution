#!/usr/bin/env node
import fs from "fs";
import path from "path";
import os from "os";
import crypto from "crypto";
import { spawn, spawnSync } from "child_process";
import { fileURLToPath } from "url";

import { triggerWebhook } from "./utils/webhook.mjs";
import { retryTest } from "./utils/retry.mjs";
import { sendFailureEmail, isEmailConfigured } from "./utils/email.mjs";
import { analyzeFailure, buildCursorReport } from "./analyzers/cursorAnalyzer.mjs";
import { callCursorAI } from "./clients/cursorApi.mjs";

// AI mode: CURSOR_API (Cloud Agents) > ATP rules > Ollama
const USE_CURSOR_AI = (process.env.USE_CURSOR_AI ?? "1") === "1";
const USE_CURSOR_API = !!(process.env.CURSOR_API_KEY && process.env.CURSOR_GITHUB_REPO);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.join(__dirname, "..");

const CONFIG = {
  appId: process.env.APP_ID || "com.kodaksmile",
  testsDir: path.resolve(process.env.TESTS_DIR || path.join(projectRoot, "tests")),
  flowsDir: path.resolve(process.env.FLOWS_DIR || path.join(projectRoot, "flows")),
  maestroBin: process.env.MAESTRO_BIN || null,
  adbBin: process.env.ADB_BIN || "adb",

  runsDir: path.resolve(process.env.RUNS_DIR || path.join(projectRoot, "ai-doctor", "artifacts")),
  historyFile: path.resolve(process.env.HISTORY_FILE || path.join(projectRoot, "ai-doctor", "failure_history.json")),

  junitRel: path.join("junit","report.xml"),
  maestroStdoutRel: path.join("maestro","maestro_stdout.log"),
  maestroStderrRel: path.join("maestro","maestro_stderr.log"),
  logcatRel: path.join("logs","logcat.txt"),
  dumpsysWindowsRel: path.join("logs","dumpsys_windows.txt"),
  dumpsysActivityRel: path.join("logs","dumpsys_activity.txt"),
  dumpsysProcessesRel: path.join("logs","dumpsys_processes.txt"),

  runFailuresJsonRel: path.join("analysis","failures.json"),
  yamlFailingTestRel: path.join("yaml","failing_test.yaml"),
  yamlTreeRel: path.join("yaml","resolved_flow_tree"),
  patchesDirRel: "patches",

  ollamaHost: (process.env.OLLAMA_HOST || "http://localhost:11434").replace(/\/$/, ""),
  ollamaModel: process.env.OLLAMA_MODEL || "llava:latest",
  useVision: (process.env.OLLAMA_VISION || "1") === "1",

  maxLogChars: 26000,
  maxYamlChars: 24000,
  maxFailureChars: 10000,

  similarityTopK: 5,
  minJaccardForSimilar: 0.22,
  maxAnalysesPerSignature: 30,
};

function ensureDir(p){ fs.mkdirSync(p,{recursive:true}); }
function exists(p){ try{ fs.accessSync(p); return true; }catch{ return false; } }
function readText(p){ return fs.readFileSync(p,"utf8"); }
function writeText(p,s){ ensureDir(path.dirname(p)); fs.writeFileSync(p,s,"utf8"); }
function writeJson(p,o){ ensureDir(path.dirname(p)); fs.writeFileSync(p,JSON.stringify(o,null,2),"utf8"); }
function loadJson(p,fallback){ try{return JSON.parse(readText(p));}catch{return fallback;} }
function nowStamp(){ const d=new Date(); const pad=n=>String(n).padStart(2,"0"); return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`; }
function sha1(s){ return crypto.createHash("sha1").update(s).digest("hex"); }
function safeTruncate(s,max){ if(!s) return ""; return s.length<=max? s : s.slice(0,max)+"\n…(truncated)…"; }
function normalizeReason(s){
  if(!s) return "";
  return s.toLowerCase()
    .replace(/0x[0-9a-f]+/g,"0x?")
    .replace(/\b[a-f0-9]{10,}\b/g,"?")
    .replace(/\b\d+(\.\d+)?\b/g,"#")
    .replace(/\s+/g," ").trim();
}
function getMaestroCmd(){
  if(CONFIG.maestroBin) return CONFIG.maestroBin;
  const p=path.join(os.homedir(),".maestro","bin","maestro");
  return fs.existsSync(p)? p : "maestro";
}

function parseJUnitXml(xmlText){
  const out=[];
  const tcRegex=/<testcase\b([^>]*)>([\s\S]*?)<\/testcase>|<testcase\b([^>]*)\/>/g;
  let m;
  while((m=tcRegex.exec(xmlText))!==null){
    const attrs=m[1]||m[3]||"";
    const body=m[2]||"";
    const name=(attrs.match(/\bname="([^"]*)"/)||[])[1]||"UNKNOWN_TEST";
    const classname=(attrs.match(/\bclassname="([^"]*)"/)||[])[1]||"";
    const time=(attrs.match(/\btime="([^"]*)"/)||[])[1]||"";
    const failureMatch=body.match(/<failure\b([^>]*)>([\s\S]*?)<\/failure>|<failure\b([^>]*)\/>/);
    const errorMatch=body.match(/<error\b([^>]*)>([\s\S]*?)<\/error>|<error\b([^>]*)\/>/);
    const node=failureMatch||errorMatch;
    let status="PASS", failType="", failMessage="", failText="";
    if(node){
      status="FAIL";
      const attrStr=node[1]||node[3]||"";
      failType=(attrStr.match(/\btype="([^"]*)"/)||[])[1]||(failureMatch?"failure":"error");
      failMessage=(attrStr.match(/\bmessage="([^"]*)"/)||[])[1]||"";
      failText=(node[2]||"").trim();
    }
    out.push({name,classname,time,status,failType,failMessage,failText});
  }
  return out;
}

async function runCapture(cmd,args){
  return await new Promise((resolve,reject)=>{
    const child=spawn(cmd,args,{shell:false});
    let out="", err="";
    child.stdout.on("data",d=>out+=d.toString("utf8"));
    child.stderr.on("data",d=>err+=d.toString("utf8"));
    child.on("error",reject);
    child.on("close",code=>resolve({code,out,err}));
  });
}

async function adbIsAvailable(){
  try{ const r=await runCapture(CONFIG.adbBin,["devices"]); return r.code===0; }catch{ return false; }
}
async function captureAndroidArtifacts(runDir){
  const logcatPath=path.join(runDir,CONFIG.logcatRel);
  const winPath=path.join(runDir,CONFIG.dumpsysWindowsRel);
  const actPath=path.join(runDir,CONFIG.dumpsysActivityRel);
  const procPath=path.join(runDir,CONFIG.dumpsysProcessesRel);

  const r1=await runCapture(CONFIG.adbBin,["logcat","-d"]); writeText(logcatPath, r1.out + (r1.err?`\n\n[stderr]\n${r1.err}`:""));
  const r2=await runCapture(CONFIG.adbBin,["shell","dumpsys","window","windows"]); writeText(winPath, r2.out + (r2.err?`\n\n[stderr]\n${r2.err}`:""));
  const r3=await runCapture(CONFIG.adbBin,["shell","dumpsys","activity"]); writeText(actPath, r3.out + (r3.err?`\n\n[stderr]\n${r3.err}`:""));
  const r4=await runCapture(CONFIG.adbBin,["shell","dumpsys","activity","processes"]); writeText(procPath, r4.out + (r4.err?`\n\n[stderr]\n${r4.err}`:""));
}

async function adbScreenshotTo(filePath){
  ensureDir(path.dirname(filePath));
  return await new Promise((resolve,reject)=>{
    const child=spawn(CONFIG.adbBin,["exec-out","screencap","-p"],{shell:false});
    const out=fs.createWriteStream(filePath,{flags:"w"});
    child.stdout.pipe(out);
    let err="";
    child.stderr.on("data",d=>err+=d.toString("utf8"));
    child.on("error",reject);
    child.on("close",code=>{
      out.end();
      if(code===0 && exists(filePath)) resolve(true);
      else reject(new Error(`adb screencap failed (code=${code}) ${err}`));
    });
  });
}

function listFilesRecursive(dir, exts){
  const out=[];
  if(!exists(dir)) return out;
  const stack=[dir];
  while(stack.length){
    const p=stack.pop();
    let st; try{ st=fs.statSync(p);}catch{continue;}
    if(st.isDirectory()){
      let items=[]; try{ items=fs.readdirSync(p);}catch{items=[];}
      for(const it of items) stack.push(path.join(p,it));
    } else {
      if(!exts || exts.includes(path.extname(p).toLowerCase())) out.push(p);
    }
  }
  return out;
}
function extractRunFlows(yamlText){
  const lines=yamlText.split(/\r?\n/);
  const out=[];
  for(const line of lines){
    const m1=line.match(/^\s*-\s*runFlow:\s*(.+)\s*$/);
    if(m1 && m1[1]) { out.push(m1[1].trim().replace(/^["']|["']$/g,"")); continue; }
    const m2=line.match(/^\s*runFlow:\s*(.+)\s*$/);
    if(m2 && m2[1]) out.push(m2[1].trim().replace(/^["']|["']$/g,""));
  }
  return out;
}
function resolveRunFlowPath(currentFile, rf){
  const v=String(rf||"").trim();
  if(!v) return null;
  if(path.isAbsolute(v)) return exists(v)? v : null;
  const relToCurrent=path.resolve(path.dirname(currentFile), v); if(exists(relToCurrent)) return relToCurrent;
  const relToRoot=path.resolve(projectRoot, v); if(exists(relToRoot)) return relToRoot;
  const relToFlows=path.resolve(CONFIG.flowsDir, v); if(exists(relToFlows)) return relToFlows;
  return null;
}
function resolveYamlTree(entry, maxFiles=250){
  const visited=new Set(); const edges=[];
  function dfs(f){
    if(!f || visited.has(f)) return;
    visited.add(f); if(visited.size>maxFiles) return;
    let txt=""; try{ txt=readText(f);}catch{return;}
    for(const rf of extractRunFlows(txt)){
      const dep=resolveRunFlowPath(f, rf);
      if(dep && [".yaml",".yml"].includes(path.extname(dep).toLowerCase())){
        edges.push({from:f,to:dep,raw:rf});
        dfs(dep);
      }
    }
  }
  dfs(entry);
  return {files:[...visited], edges};
}
function copyYamlTree(entry, destFolder){
  ensureDir(destFolder);
  const {files,edges}=resolveYamlTree(entry);
  const map={};
  for(const f of files){
    const id=sha1(f).slice(0,10);
    const newName=`${path.basename(f,path.extname(f))}__${id}${path.extname(f)}`;
    const dest=path.join(destFolder,newName);
    try{ fs.copyFileSync(f,dest); map[f]=dest; }catch{}
  }
  const manifest={
    entry: path.relative(projectRoot, entry),
    copied_entry: map[entry]? path.relative(projectRoot,map[entry]) : null,
    file_count: files.length,
    files: files.map(f=>({original:path.relative(projectRoot,f), copied: map[f]? path.relative(projectRoot,map[f]) : null})),
    edges: edges.map(e=>({from:path.relative(projectRoot,e.from), to:path.relative(projectRoot,e.to), raw:e.raw}))
  };
  writeJson(path.join(destFolder,"_yaml_tree_manifest.json"), manifest);
  return manifest;
}
function findTestYaml(testName){
  const testFiles=listFilesRecursive(CONFIG.testsDir, [".yaml",".yml"]);
  for(const f of testFiles){
    let txt=""; try{ txt=readText(f);}catch{continue;}
    const m=txt.match(/^\s*name:\s*(.+)\s*$/m);
    if(m && m[1] && m[1].trim()===testName.trim()) return f;
  }
  for(const f of testFiles){
    let txt=""; try{ txt=readText(f);}catch{continue;}
    if(txt.includes(testName)) return f;
  }
  return null;
}

function keywordize(text){
  const stop=new Set(["the","a","an","and","or","to","of","in","on","for","with","is","are","was","were","be","been","it","this","that","as","at","by","from","not"]);
  const tokens=(text||"").toLowerCase().replace(/[^a-z0-9]+/g," ").split(" ").map(t=>t.trim()).filter(t=>t && t.length>=3 && !stop.has(t));
  const freq=new Map();
  for(const t of tokens) freq.set(t,(freq.get(t)||0)+1);
  return [...freq.entries()].sort((a,b)=>b[1]-a[1]).slice(0,30).map(([k])=>k);
}
function jaccard(a,b){
  const A=new Set(a||[]), B=new Set(b||[]);
  if(!A.size && !B.size) return 0;
  let inter=0; for(const x of A) if(B.has(x)) inter++;
  const uni=A.size+B.size-inter;
  return uni? inter/uni : 0;
}

async function ollamaGenerate(prompt, imagesBase64){
  const url=`${CONFIG.ollamaHost}/api/generate`;
  const payload={model:CONFIG.ollamaModel, prompt, stream:false};
  if(imagesBase64?.length) payload.images=imagesBase64;
  const res=await fetch(url,{method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
  if(!res.ok) throw new Error(`Ollama /generate failed: ${res.status} ${await res.text()}`);
  const data=await res.json();
  return data?.response ?? "";
}

const SCHEMA_EXAMPLE = {
  failure_summary: "Short summary",
  root_causes: [{ cause: "Cause", confidence: 0.0, evidence: ["..."] }],
  fixes: [{ priority: "P0|P1|P2", type: "environment|selectors|timing|navigation|permissions|bluetooth|app_crash|data|other", change: "Action", why: "Why", patch: { file: "relative/path.yaml", diff: "unified diff optional" } }],
  maestro_yaml_improvements: ["..."],
  next_run_experiments: ["..."],
  fingerprint_keywords: ["..."],
  regression_check: { same_as_before: true, what_changed: "..." },
  retryRecommended: false
};

function buildPrompt(ctx){
  return `
You are a senior Mobile QA Automation engineer + Maestro expert + Android debugging expert.

Return ONLY valid JSON (no markdown) that matches this schema exactly:
${JSON.stringify(SCHEMA_EXAMPLE, null, 2)}

Context:
AppId: ${CONFIG.appId}
Testcase: ${ctx.test.name}
Screenshot attached: ${ctx.hasScreenshot ? "YES" : "NO"}

JUnit message:
${safeTruncate(ctx.failMessage||"", 2500)}

JUnit text:
${safeTruncate(ctx.failText||"", CONFIG.maxFailureChars)}

Maestro stdout:
${safeTruncate(ctx.maestroStdout||"", CONFIG.maxLogChars)}

Maestro stderr:
${safeTruncate(ctx.maestroStderr||"", CONFIG.maxLogChars)}

logcat:
${safeTruncate(ctx.logcat||"", CONFIG.maxLogChars)}

dumpsys window:
${safeTruncate(ctx.dumpsysWindows||"", CONFIG.maxLogChars)}

dumpsys activity:
${safeTruncate(ctx.dumpsysActivity||"", CONFIG.maxLogChars)}

dumpsys processes:
${safeTruncate(ctx.dumpsysProcesses||"", CONFIG.maxLogChars)}

Failing YAML:
${safeTruncate(ctx.failingYaml||"", CONFIG.maxYamlChars)}

YAML tree manifest:
${safeTruncate(JSON.stringify(ctx.yamlTreeManifest||{},null,2), CONFIG.maxYamlChars)}

Previous analyses (same signature):
${ctx.previousAnalyses?.length ? ctx.previousAnalyses.map(x=>JSON.stringify(x.analysis,null,2)).join("\n\n") : "None"}

Similar failures:
${ctx.similarFailures?.length ? ctx.similarFailures.map(x=>`score=${x.score.toFixed(3)}\n${JSON.stringify(x.analysisPreview,null,2)}`).join("\n\n") : "None"}
`.trim();
}

function defaultHistory(){ return {version:3, createdAt:new Date().toISOString(), signatures:{}, testState:{}, runs:[]}; }

function runMaestroLive(testsDir, reportPath, stdoutLog, stderrLog){
  const maestroCmd=getMaestroCmd();
  const cmd = `${maestroCmd} test "${testsDir}" --format junit --output "${reportPath}" 2> "${stderrLog}" | tee "${stdoutLog}"`;
  const r=spawnSync("bash",["-lc",cmd],{cwd:projectRoot, stdio:"inherit"});
  return r.status ?? 1;
}

async function captureFailureScreenshot(failureDir, testName){
  const screenshotsDir=path.join(failureDir,"screenshots"); ensureDir(screenshotsDir);
  const safeName=testName.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"");
  const outPath=path.join(screenshotsDir,`${safeName||"failure"}.png`);
  await adbScreenshotTo(outPath);
  return outPath;
}

function writePatchFiles(failureDir, signature, fixes){
  const patchDir=path.join(failureDir, CONFIG.patchesDirRel, signature);
  ensureDir(patchDir);
  const written=[];
  if(!Array.isArray(fixes)) return written;
  for(let i=0;i<fixes.length;i++){
    const diff=fixes[i]?.patch?.diff;
    const file=fixes[i]?.patch?.file || "unknown";
    if(!diff || typeof diff!=="string" || diff.trim().length<10) continue;
    const safeFile=file.replace(/[\\\/:]+/g,"_").replace(/[^a-zA-Z0-9_.-]+/g,"_");
    const patchPath=path.join(patchDir,`fix_${String(i+1).padStart(2,"0")}__${safeFile}.diff`);
    writeText(patchPath,diff);
    written.push(path.relative(projectRoot, patchPath));
  }
  return written;
}

async function main(){
  ensureDir(CONFIG.runsDir);
  if(!exists(CONFIG.testsDir)){ console.error("❌ tests folder not found:", CONFIG.testsDir); process.exit(2); }

  const runId=`run-${nowStamp()}`;
  const runDir=path.join(CONFIG.runsDir, runId);
  ensureDir(runDir);

  const junitPath=path.join(runDir, CONFIG.junitRel);
  const stdoutLog=path.join(runDir, CONFIG.maestroStdoutRel);
  const stderrLog=path.join(runDir, CONFIG.maestroStderrRel);

  console.log("🧠 AI Doctor (single script) started");
  const aiMode = USE_CURSOR_API ? "Cursor Cloud Agents API" : USE_CURSOR_AI ? "Cursor AI (ATP-based)" : "Ollama";
  console.log("📋 Using", aiMode, "for analysis");
  const status=runMaestroLive(CONFIG.testsDir, junitPath, stdoutLog, stderrLog);
  console.log(status===0 ? "✅ Maestro PASS" : "❌ Maestro FAIL (continuing analysis)");

  if(!exists(junitPath)){ console.error("❌ report.xml not generated:", junitPath); process.exit(2); }

  const history=loadJson(CONFIG.historyFile, defaultHistory());

  const adbOk=await adbIsAvailable();
  if(adbOk){
    try{ await captureAndroidArtifacts(runDir); }catch(e){ console.log("⚠️ captureAndroidArtifacts failed:", String(e)); }
  } else {
    console.log("⚠️ ADB not available. Skipping screenshots/logcat/dumpsys.");
  }

  const cases=parseJUnitXml(readText(junitPath));
  const failures=cases.filter(c=>c.status==="FAIL");
  const passes=cases.filter(c=>c.status==="PASS");

  for(const p of passes){
    const prev=history.testState?.[p.name]?.activeSignature;
    if(prev && history.signatures?.[prev]){
      history.signatures[prev].active=false;
      history.signatures[prev].resolvedAt=new Date().toISOString();
      history.testState[p.name].activeSignature=null;
    }
  }

  const maestroStdout=exists(stdoutLog)? readText(stdoutLog):"";
  const maestroStderr=exists(stderrLog)? readText(stderrLog):"";
  const logcat=exists(path.join(runDir,CONFIG.logcatRel))? readText(path.join(runDir,CONFIG.logcatRel)):"";
  const dumpsysWindows=exists(path.join(runDir,CONFIG.dumpsysWindowsRel))? readText(path.join(runDir,CONFIG.dumpsysWindowsRel)):"";
  const dumpsysActivity=exists(path.join(runDir,CONFIG.dumpsysActivityRel))? readText(path.join(runDir,CONFIG.dumpsysActivityRel)):"";
  const dumpsysProcesses=exists(path.join(runDir,CONFIG.dumpsysProcessesRel))? readText(path.join(runDir,CONFIG.dumpsysProcessesRel)):"";

  const runFailures=[];
  for(const f of failures){
    const combined=`${f.failMessage||""}\n${f.failText||""}`.trim();
    const normalized=normalizeReason(combined);
    const signature=sha1(`${f.name}|${normalized}`.slice(0,8000));
    const failureDir=path.join(runDir,"failures",signature);
    ensureDir(failureDir);

    const testYamlPath=findTestYaml(f.name);
    let failingYaml="";
    let yamlTreeManifest=null;
    if(testYamlPath && exists(testYamlPath)){
      failingYaml=readText(testYamlPath);
      const copyPath=path.join(failureDir, CONFIG.yamlFailingTestRel);
      ensureDir(path.dirname(copyPath));
      fs.copyFileSync(testYamlPath, copyPath);
      yamlTreeManifest=copyYamlTree(testYamlPath, path.join(failureDir, CONFIG.yamlTreeRel));
    }

    let screenshotPath=null;
    if(adbOk){
      try{ screenshotPath=await captureFailureScreenshot(failureDir, f.name); }catch{}
    }

    const prevRec=history.signatures?.[signature];
    const previousAnalyses=prevRec?.analyses ? [...prevRec.analyses].slice(-3).reverse().map(x=>({timestamp:x.timestamp, analysis:x.analysis})) : [];

    const thisKeywords=keywordize(`${f.name} ${combined} ${maestroStderr} ${logcat}`.slice(0,35000));
    const candidates=[];
    for(const [sig, rec] of Object.entries(history.signatures||{})){
      if(!rec || sig===signature) continue;
      const score=jaccard(thisKeywords, rec.keywords||[]);
      if(score>=CONFIG.minJaccardForSimilar){
        const last=rec.analyses?.length ? rec.analyses[rec.analyses.length-1]?.analysis : null;
        candidates.push({signature:sig, score, analysisPreview:last?{failure_summary:last.failure_summary, fixes:(last.fixes||[]).slice(0,2), root_causes:last.root_causes}:null});
      }
    }
    candidates.sort((a,b)=>b.score-a.score);
    const similarFailures=candidates.slice(0, CONFIG.similarityTopK);

    let analysis=null;
    if(USE_CURSOR_API){
      const prompt=buildPrompt({
        test:f,
        hasScreenshot:Boolean(screenshotPath && exists(screenshotPath)),
        failMessage:f.failMessage,
        failText:f.failText,
        maestroStdout, maestroStderr,
        logcat, dumpsysWindows, dumpsysActivity, dumpsysProcesses,
        failingYaml,
        yamlTreeManifest,
        previousAnalyses,
        similarFailures
      });
      const imagesBase64=(screenshotPath && exists(screenshotPath)) ? [fs.readFileSync(screenshotPath).toString("base64")] : [];
      try {
        const cursorResult=await callCursorAI({prompt, images:imagesBase64});
        analysis={
          failure_summary:cursorResult.rootCause||"",
          root_causes:[{cause:cursorResult.rootCause||"", confidence:cursorResult.confidence||0.7, evidence:[cursorResult.suggestedFix||""]}],
          fixes:[{priority:"P1", type:cursorResult.failureType||"other", change:cursorResult.suggestedFix||"", why:cursorResult.rootCause||"", patch:null}],
          maestro_yaml_improvements:[],
          next_run_experiments:[],
          fingerprint_keywords:thisKeywords.slice(0,12),
          regression_check:{same_as_before:Boolean(prevRec), what_changed:""},
          retryRecommended:Boolean(cursorResult.retryRecommended)
        };
      } catch(e){
        console.log("❌ Cursor API failed:", e?.message||e, "- falling back to ATP rules");
        const cursorResult=analyzeFailure(f.name, `${f.failMessage||""}\n${f.failText||""}`.trim(), failingYaml);
        analysis={
          failure_summary:cursorResult.rootCause,
          root_causes:[{cause:cursorResult.rootCause, confidence:cursorResult.confidence, evidence:[cursorResult.suggestedFix]}],
          fixes:[{priority:"P1", type:cursorResult.failureType, change:cursorResult.suggestedFix, why:cursorResult.rootCause, patch:null}],
          maestro_yaml_improvements:[],
          next_run_experiments:[],
          fingerprint_keywords:thisKeywords.slice(0,12),
          regression_check:{same_as_before:Boolean(prevRec), what_changed:""},
          retryRecommended:cursorResult.retryRecommended
        };
      }
    } else if(USE_CURSOR_AI){
      const cursorResult=analyzeFailure(f.name, `${f.failMessage||""}\n${f.failText||""}`.trim(), failingYaml);
      analysis={
        failure_summary:cursorResult.rootCause,
        root_causes:[{cause:cursorResult.rootCause, confidence:cursorResult.confidence, evidence:[cursorResult.suggestedFix]}],
        fixes:[{priority:"P1", type:cursorResult.failureType, change:cursorResult.suggestedFix, why:cursorResult.rootCause, patch:null}],
        maestro_yaml_improvements:[],
        next_run_experiments:[],
        fingerprint_keywords:thisKeywords.slice(0,12),
        regression_check:{same_as_before:Boolean(prevRec), what_changed:""},
        retryRecommended:cursorResult.retryRecommended
      };
    } else {
      let imagesBase64=null;
      if(CONFIG.useVision && screenshotPath && exists(screenshotPath)) imagesBase64=[fs.readFileSync(screenshotPath).toString("base64")];
      const prompt=buildPrompt({
        test:f,
        hasScreenshot:Boolean(imagesBase64?.length),
        failMessage:f.failMessage,
        failText:f.failText,
        maestroStdout, maestroStderr,
        logcat, dumpsysWindows, dumpsysActivity, dumpsysProcesses,
        failingYaml,
        yamlTreeManifest,
        previousAnalyses,
        similarFailures
      });
      let responseRaw="";
      try{ responseRaw=await ollamaGenerate(prompt, imagesBase64); analysis=JSON.parse(responseRaw); }
      catch(e){
        analysis={...SCHEMA_EXAMPLE, failure_summary:"Ollama failed/invalid JSON.", root_causes:[{cause:"Ollama failure", confidence:0.2, evidence:[String(e)]}], fingerprint_keywords:thisKeywords.slice(0,12), regression_check:{same_as_before:Boolean(prevRec), what_changed:""}, retryRecommended:false, _raw:safeTruncate(responseRaw||"",8000)};
      }
    }

    const patchFiles=writePatchFiles(failureDir, signature, analysis?.fixes||[]);
    const finalKeywords=Array.isArray(analysis?.fingerprint_keywords)&&analysis.fingerprint_keywords.length? analysis.fingerprint_keywords.slice(0,25): thisKeywords.slice(0,25);

    if(!history.signatures[signature]){
      history.signatures[signature]={testName:f.name, normalizedReason:normalized, keywords:finalKeywords, firstSeen:new Date().toISOString(), lastSeen:new Date().toISOString(), occurrences:0, active:true, resolvedAt:null, analyses:[]};
    }
    const sigRec=history.signatures[signature];
    sigRec.lastSeen=new Date().toISOString();
    sigRec.occurrences+=1;
    sigRec.active=true;
    sigRec.keywords=finalKeywords;
    sigRec.analyses.push({
      timestamp:new Date().toISOString(),
      runId,
      prompt,
      responseRaw,
      analysis,
      artifacts:{ junitPath:path.relative(projectRoot,junitPath), maestroStdoutPath:path.relative(projectRoot,stdoutLog), maestroStderrPath:path.relative(projectRoot,stderrLog), screenshotPath:screenshotPath?path.relative(projectRoot,screenshotPath):null, testYamlPath:testYamlPath?path.relative(projectRoot,testYamlPath):null },
      patchFiles
    });
    if(sigRec.analyses.length>CONFIG.maxAnalysesPerSignature) sigRec.analyses=sigRec.analyses.slice(sigRec.analyses.length-CONFIG.maxAnalysesPerSignature);

    history.testState[f.name]={activeSignature:signature};

    runFailures.push({testName:f.name, signature, summary:analysis?.failure_summary||"", failureMessage:`${f.failMessage||""}\n${f.failText||""}`.trim(), fixes:(analysis?.fixes||[]).slice(0,6), screenshotPath:screenshotPath?path.relative(projectRoot,screenshotPath):null, patchFiles, keywords:finalKeywords, retryRecommended:Boolean(analysis?.retryRecommended)});
  }

  const runFailuresPath=path.join(runDir, CONFIG.runFailuresJsonRel);
  writeJson(runFailuresPath, runFailures);

  history.runs.push({runId, timestamp:new Date().toISOString(), summary:{pass:passes.length, fail:failures.length}, runDir:path.relative(projectRoot,runDir), junitPath:path.relative(projectRoot,junitPath), runFailuresJson:path.relative(projectRoot,runFailuresPath)});
  writeJson(CONFIG.historyFile, history);

  const latestReport={runId, timestamp:new Date().toISOString(), pass:passes.length, fail:failures.length, failures:runFailures, artifactsDir:path.relative(projectRoot,runDir), historyFile:path.relative(projectRoot,CONFIG.historyFile)};
  const latestPath=path.join(CONFIG.runsDir,"latest-ai-report.json");
  writeJson(latestPath, latestReport);

  if((USE_CURSOR_AI || USE_CURSOR_API) && runFailures.length>0){
    const cursorResult={failuresCount:failures.length, retryRecommended:runFailures.some(r=>r.retryRecommended), resultsByFlow:runFailures.map(r=>({flowName:r.testName, failureMessage:r.failureMessage||r.summary, rootCause:r.summary, suggestedFix:(r.fixes||[])[0]?.change||r.summary, retryRecommended:r.retryRecommended, screenshots:[]}))};
    const cursorReport=buildCursorReport(cursorResult);
    const cursorPath=path.join(CONFIG.runsDir,"cursor-report.md");
    writeText(cursorPath, cursorReport);
    console.log("📄 Cursor report:", cursorPath);
  }

  console.log(`\nRun: ${runId} PASS=${passes.length} FAIL=${failures.length}`);
  console.log(`Artifacts: ${runDir}`);
  console.log(`Latest report: ${latestPath}`);
  console.log(`History DB: ${CONFIG.historyFile}`);

  try{
    if(failures.length && isEmailConfigured()){
      await sendFailureEmail({subject:`Maestro FAIL (${failures.length}) - ${runId}`, body:JSON.stringify(latestReport,null,2)});
      console.log("📧 Failure email sent.");
    }
  }catch(e){ console.log("📧 Email send failed:", e?.message||e); }

  if(runFailures.some(x=>x.retryRecommended)){
    console.log("🔁 Retry triggered by AI");
    await retryTest();
  }

  await triggerWebhook(latestReport);

  process.exit(failures.length?1:0);
}

main().catch(e=>{ console.error("❌ AI Doctor crashed:", e); process.exit(3); });
