# Maestro — official reference (this repo)

**Source of truth:** [Maestro documentation](https://docs.maestro.dev/)

Especially:

| Topic | Link |
|--------|------|
| CLI (all flags) | [Maestro CLI commands and options](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options) |
| Flows & `config.yaml` | [Maestro Docs → Flows / workspace](https://docs.maestro.dev/) |

**Syntax in this repo:** Use **space-separated** flags and values, e.g. `--format junit --output report.xml` (not `--format=junit` / `--output=report.xml`). The [CLI reference](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options) lists option names in tables; **invoke** them with a space before each value, as in the examples below.

## Commands used in this project

Aligned with the CLI docs: **global options before `test`**, **space-separated** `test` options where a value is needed.

### Run whole suite (from repo root, uses `config.yaml`)

```bash
maestro test . --format junit --output report.xml
```

### Run one flow file

From repo root; **`--config`** points at the workspace so included `runFlow` paths resolve like local runs:

```bash
maestro test "Non printing flows/flow1.yaml" --config config.yaml
```

### Run on a specific device (official global flag)

```bash
maestro --device <SERIAL> test "Non printing flows/flow1.yaml" --format junit --output reports/raw/nonprinting/flow1_device.xml
```

`--device` / `--udid` are **global** options; place them **before** `test` (see [CLI commands and options](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options)).

### Optional workspace config

```bash
maestro test . --config config.yaml --format junit --output report.xml
```

### Debug artifacts

Per `test` subcommand: `--debug-output <path>` (see official table under `test` on the CLI page).

---

**Batch/PowerShell wrappers** in `scripts/` use the same **space-separated** flag style. When updating wrappers, re-check the official CLI page for changes.
