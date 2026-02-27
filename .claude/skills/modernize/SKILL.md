---
name: modernize
description: >
  Modernization radar + upgrade planning. Identify deprecations, EOL runtimes, and outdated
  patterns; produce a prioritized modernization backlog and safe upgrade path. By default,
  do not refactor for readability, do not do bug-risk refactors, and do not perform dependency
  upgrade sweeps unless explicitly requested.
---

# Modernize Doctor (Planning-First, Low-Churn)

## Mission

Run a **modernization assessment**

- Detect **deprecated APIs** and framework patterns that will break soon
- Detect **EOL / soon-to-be-EOL** runtimes and major ecosystem shifts
- Identify **outdated implementations** where a modern standard exists
- Produce a **prioritized backlog** and a **safe upgrade plan** (with guardrails)

This skill is intentionally **not** a refactor pass.

## Explicit Non-Goals (avoid overlap with refactor)

Do **not**:

- Perform readability refactors, renames, or code cleanup
- Perform bug-risk scanning/fixing as a general pass
- Remove dead/deprecated code as a cleanup exercise
- Add/modify verification scripts or test harnesses
- Do broad dependency upgrade sweeps (patch/minor upgrades) by default

If any of the above is needed, keep track of such and let me know to hand off to the refactor skill.

## Inputs

Collect:

- Languages/frameworks + runtime versions (Node/Python/etc.)
- Dependency manifests and lockfiles
- CI/workflow configuration (runtime versions used in CI)
- Any pinned infra/tooling constraints (deployment platform, container base image, etc.)

## Phase 0 — Modernization Inventory (read-only)

Report:

- Runtime targets (Node/Python/etc.) and their support status (EOL/soon EOL/active)
- Top-level frameworks/libs that frequently deprecate APIs (Next.js, FastAPI, etc.)
- Tooling baseline (TypeScript, ESLint, formatter, build tooling)

## Phase 1 — Deprecation & Drift Map (read-only)

Identify:

- Deprecation warnings in code/comments/config
- Deprecated APIs used in framework or SDK calls
- Deprecated config keys in tooling (lint/build/test)
- Patterns that are still "working" but no longer recommended

Output a list:

- What is deprecated
- Where it appears (file + symbol)
- Suggested replacement (one-liner)
- Risk level (low/med/high)
- Whether it is blocking future upgrades

## Phase 2 — Upgrade Opportunities (plan only)

For each major component (runtime/framework/core libs):

- Current version → recommended target
- What breaks (high-level)
- Migration steps (checklist)
- Estimated effort (S/M/L)
- Suggested sequencing (what must happen first)

Important:

- Do not apply major upgrades in this skill.
- Do not apply minor/patch upgrades unless explicitly requested.

## Phase 3 — “Better Primitive” Suggestions (plan only)

Flag places where modern standard primitives reduce maintenance burden, without rewriting now:

- Replace custom utility with standard library / well-adopted library
- Replace outdated patterns with current recommended patterns

Keep suggestions concrete:

- before/after API call shape
- exact files to touch
- why it matters (maintenance, compatibility, future upgrades)

## Outputs

Deliver:

1. **Modernization Backlog** (prioritized)

   - Item, location, risk, why, suggested fix

2. **Upgrade Plan**

   - Recommended sequencing and checkpoints

3. **Do-Now vs Do-Later**

   - Quick wins (low risk, unblocking)
   - Major migrations (plan only)

4. **Explicit “No Changes Applied” statement**
   - Unless the user explicitly requested applying specific upgrades

## Optional Mode: Apply a Single Targeted Modernization

Only if explicitly requested (e.g., “modernize Next.js config warnings”):

- Apply the smallest change set for that single target
- Keep diffs tight
- No broad refactors
- Note how to verify (but do not add new scripts)

## Stop Conditions

Stop and report (do not change code) when:

- The only path forward is a major upgrade/migration
- Constraints are unclear (deployment/runtime pinned)
- The change would overlap with refactor responsibilities
