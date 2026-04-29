# Kodak Smile ATP Maestro Generated Flows

Generated from: Kodak_Smile_Plus_ATP_Transformed.xlsx
Total ATP test cases generated: 104

Folder:
- `ATP TestCase Flows/` contains one Maestro YAML file per ATP TestCaseID.
- Existing reusable flows are kept under `flows/`, `Non printing flows/`, and `Printing Flow/`.
- `ATP_TestCase_Maestro_Mapping.csv` maps ATP IDs to generated YAML files.

Important:
1. Your original ZIP did not include `elements/loadElements.yaml`, but many flows reference it.
   Add your real `elements/loadElements.yaml` before running these flows.
2. Hardware cases like no paper, paper jam, overheated printer, Bluetooth disabled, device powered off, and out-of-range still need real device/printer setup.
3. Some ATP steps such as Date Picker and Facebook login may need app-specific selectors.
4. Each generated flow includes screenshots before/after ATP steps to help Jenkins/AI reporting identify failure location.

Suggested run:
`maestro test "ATP TestCase Flows/SignUp_Login/TC_SU_01_Skip account creation.yaml" --device <deviceId>`
