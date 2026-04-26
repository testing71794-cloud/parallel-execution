Kodak Smile Parallel Continue Pipeline - Fixed Package

This corrected package addresses:
1. Jenkins still using old sequential path
2. Bluetooth pairing popup handling too narrow
3. Excel report reading wrong folder
4. Same-machine parallel wait loop could hang forever
5. Old temp/failed flags not cleaned before next run

Files included
- Jenkinsfile
- flows/handleBluetoothPairing.yaml
- scripts/precheck_environment.bat
- scripts/run_one_flow_on_device.bat
- scripts/run_suite_parallel_same_machine.bat
- scripts/generate_build_summary.py
- scripts/generate_excel_report.py
- scripts/run_ai_analysis.bat
- docs/PIPELINE_EXECUTION_AND_EMAIL.md

Important
- Configure Jenkins job to use Jenkinsfile
- Do not use Jenkinsfile.hybrid
- Do not call scripts/run_all_flows_pipeline.bat for the new flow
