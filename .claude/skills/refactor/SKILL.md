---
name: refactor
description: >
  Safe readability refactor + bug-risk review + outdated dependency audit for any codebase.
  Improves diagnostics and adds/updates lightweight verification scripts without changing external behavior.
  Removes deprecated, unused, and unreachable code.
---

# Refactor Doctor (General, Bun-Aware)

## Mission

Perform a **safe readability refactor**, then a **bug-risk + dependency audit**, and finish with **verification**.

Supports: Python, Node/TS (npm/yarn/pnpm/bun), Go, Java, Rust, mixed monorepos.

---

## Non-Negotiables

1. **Do not change component inputs/outputs.** Function signatures, API request/response shapes, props interfaces, return types, event payloads, SSE formats, and database schemas must remain identical. If a function takes X and returns Y before refactor, it must take X and return Y after.
2. Do not change external behavior (APIs, CLIs, outputs, formats) unless explicitly asked.
3. Prefer small, reviewable changes.
4. Maintain backwards compatibility unless the repo clearly targets a breaking upgrade.
5. Every change must improve readability, reliability, or fix a proven issue.
6. If code/tests cannot be executed, keep changes conservative and state what was not verified.
7. **No semantic changes.** Refactoring means restructuring code for clarity without altering what it does. Do not "fix" logic, add validation, change error messages, or alter control flow unless it is a proven bug.

---

# Phase 0 — Repo Triage

Identify:

- Primary language(s)
- Entrypoints (server, CLI, build scripts)
- Dependency manifests:
  - Node: `package.json`, lockfiles
  - Python: `pyproject.toml`, `requirements.txt`
  - Go: `go.mod`
  - Rust: `Cargo.toml`
  - Java: `pom.xml`, `build.gradle`
- Existing checks (lint, test, CI, Makefile)

### Node Package Manager Detection (priority)

1. `bun.lockb` or `packageManager` indicates bun → **bun**
2. `pnpm-lock.yaml` → **pnpm**
3. `yarn.lock` → **yarn**
4. Otherwise → **npm**

Write a short **golden path** explaining how the project is normally run and tested.

---

# Phase 1 — Safe Readability Refactor

Focus on:

- Reducing nesting
- Extracting helpers
- Removing duplication
- Improving naming
- Adding type hints/interfaces where applicable
- Adding docstrings for non-obvious logic
- Normalizing error handling (no swallowed exceptions)
- Improving logs (include context like module/function/request id)
- **Removing dead code** (see Dead Code Removal below)

### Dead Code Removal

Identify and remove:

- **Unused functions/methods** — defined but never called anywhere in the codebase
- **Deprecated code** — marked with `@deprecated`, `# deprecated`, `// deprecated`, or similar annotations that has no remaining callers
- **Unreachable code** — statements after unconditional `return`/`raise`/`throw`/`break`/`continue`, dead branches behind constant conditions (e.g., `if False`, `if 0`), or feature-flagged code where the flag is permanently off
- **Unused imports/variables** — imports that are never referenced, variables assigned but never read
- **Orphaned helpers/utilities** — internal functions that only served code that has since been removed
- **Stale commented-out code** — large blocks of commented-out code with no associated TODO or explanation

Rules for dead code removal:

- Confirm the code is truly unused by searching for all references (callers, imports, dynamic dispatch, reflection, serialization) before removing.
- Be cautious with public API surfaces — only remove if the function is clearly internal or has zero external consumers.
- For libraries/packages, check exported symbols; do not remove anything that is part of the public interface unless explicitly requested.
- If removal is uncertain (e.g., called via reflection, string-based dispatch, or plugin systems), flag it in the report instead of deleting.
- Group related removals into a single reviewable change.

Rules:

- Avoid touching unrelated files.
- Avoid large formatting churn unless formatter is already standard.
- New tooling must be optional and documented.

---

# Phase 2 — Bug-Risk Scan

Look for:

- Unhandled async exceptions
- Blocking calls in async contexts
- Missing timeouts/retries (network/DB/model calls)
- Race conditions/shared mutable state
- Path handling issues
- Hidden error handling
- Boundary/off-by-one bugs
- Serialization mismatches
- Dependency API drift

When fixing:

- Provide minimal repro steps
- Add small test or smoke check if feasible

---

# Phase 3 — Dependency Audit (Practical)

Goal: actionable recommendations. Do **not** blindly upgrade.

### Node

Use detected manager:

- **bun**
  - `bun install`
  - `bun pm ls`
  - Outdated: compare `package.json` ranges vs lockfile; optionally use `bun update` in branch
- **pnpm** → `pnpm outdated`
- **yarn** → `yarn outdated`
- **npm** → `npm outdated`

### Python

Use project environment:

- `pip list --outdated`
- Prefer Poetry/uv workflow if present

### Categorize Recommendations

- Safe (patch/minor)
- Needs review (major/breaking)
- Security critical (if indicated)

---

# Phase 4 — Verification

Run existing checks first:

### Node

- bun → `bun run lint`, `bun test`
- pnpm → `pnpm -s run lint`, `pnpm -s test`
- yarn → `yarn lint`, `yarn test`
- npm → `npm -s run lint`, `npm test`

### Others

- `pytest`
- `cargo test`
- `go test`
- `make test`
