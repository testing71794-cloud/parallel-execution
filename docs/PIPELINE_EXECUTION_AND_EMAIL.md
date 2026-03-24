# Kodak Smile Parallel Continue Pipeline - Fixed

## Required changes included
- cleaned Jenkinsfile entry path
- fixed Bluetooth pairing flow variants
- suite report generation now reads from status/
- same-machine wait loop now has timeout
- temp runner and failed files are cleaned before each run

## What to change in Jenkins
- Job type: Pipeline
- Script Path: Jenkinsfile

## What not to use
- Jenkinsfile.hybrid
- scripts/run_all_flows_pipeline.bat

## Recommended run
- RUN_MODE = multi_agent_parallel
- SUITE = both
- RETRY_FAILED = true
- AI_ANALYSIS = true
