Kodak Smile Parallel Continue Pipeline

This package is designed for the exact requirement:
- parallel execution
- pipeline continues even if one flow fails
- clean top-level stage view like:
  Fetch Code -> Install Dependencies -> Execute Non Printing -> Generate Excel Report -> Execute Printing -> Generate Excel Report -> AI Analysis -> Archive -> Finalize

Supported modes
1. multi_agent_parallel
   - recommended
   - one Jenkins agent per device
   - fast + stable

2. same_machine_parallel
   - one Windows machine controls both devices in parallel
   - pipeline still continues on failures
   - less stable than multi-agent, but supported

Included files
- Jenkinsfile
- scripts/precheck_environment.bat
- scripts/run_one_flow_on_device.bat
- scripts/run_suite_parallel_same_machine.bat
- scripts/generate_build_summary.py
- scripts/generate_excel_report.py
- scripts/run_ai_analysis.bat
- README.txt
- docs/PIPELINE_EXECUTION_AND_EMAIL.md

Important behavior
- flow failures do not stop the pipeline immediately
- failure flags are created
- next flow continues
- final result is set only in Finalize Build Result
