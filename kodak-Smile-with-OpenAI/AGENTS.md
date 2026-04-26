# Instructions for AI assistants and contributors

## Every time you change Maestro-related files

**Every time** you edit any of the following, cross-check **[Maestro documentation](https://docs.maestro.dev/)** (do not guess flags or YAML keywords):

- `**/*.yaml`, `**/*.yml`, `config.yaml`
- `scripts/*.bat`, `scripts/*.ps1`, `**/*.sh` that call `maestro`
- `Jenkinsfile*`, CI config that runs Maestro

**Primary references:**

1. [Maestro CLI commands and options](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options)
2. [Maestro Docs (Flows, workspace, etc.)](https://docs.maestro.dev/)

Repo cheat sheet: `docs/MAESTRO_OFFICIAL_REFERENCE.md`

---

This file is intentionally short so tools and humans see the rule **every time** they work in this repository.
