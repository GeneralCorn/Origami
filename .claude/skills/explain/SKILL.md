---
name: explain
description: Explain the architecture, files, or concepts of the current repository. Supports full repo overview, specific file explanation, or deep explanation of a repo-related topic for learning or interview prep.
---

# Explain Skill

## Purpose

Provide clear, structured explanations of:

- The entire repository (`/explain`)
- A specific file (`/explain path/to/file`)
- A repository-related topic (`/explain <concept>`)

This skill prioritizes clarity, structure, and correctness over verbosity.

---

# Invocation Modes

## 1️⃣ `/explain`

If no argument is provided:

### Step 1: Repo Triage

- Identify primary language(s)
- Identify entrypoints (main server, CLI, app root)
- Identify dependency manifests
- Identify architectural patterns (MVC, layered, RAG pipeline, monorepo, etc.)

### Step 2: Produce Structured Overview

Output sections:

1. High-Level Purpose
2. Architecture Diagram (text-based)
3. Key Modules and Their Responsibilities
4. Data Flow (request lifecycle)
5. State & Persistence (DB/files/cache/etc.)
6. External Integrations
7. Where to Look First (for new contributors)
8. Risks / Complex Areas
9. Suggested Interview Talking Points (if applicable)

Keep this concise but complete.

---

## 2️⃣ `/explain <file>`

If the argument matches a file path:

### Step 1: Locate the file

If ambiguous, choose best match and state assumption.

### Step 2: Explain in layers

1. What this file is responsible for
2. How it fits into overall architecture
3. Important functions/classes
4. Control flow
5. External dependencies
6. Hidden assumptions / gotchas
7. If refactoring: what would improve it

If code is complex:

- Break into logical sections
- Explain flow in order of execution

Do not rewrite the file unless asked.

---

## 3️⃣ `/explain <concept>`

If argument does not match a file:

Interpret as a concept related to the repository.

Examples:

- `/explain langgraph components`
- `/explain auth flow`
- `/explain caching strategy`
- `/explain streaming architecture`

### Step 1: Scope to this repo

Explain:

- How the concept is implemented here
- Which files are involved
- How data moves through it

### Step 2: Provide Interview-Ready Summary

Include:

- What problem it solves
- Why this design was chosen
- Tradeoffs
- Common pitfalls
- How to improve it

If the concept exists in theory but not in this repo:

- Clarify that
- Provide conceptual explanation
- Suggest how it would integrate here

---

# Explanation Style Rules

- Be structured (use sections and bullets)
- Prefer diagrams in text form when helpful
- Avoid generic textbook explanations unless necessary
- Always tie explanations back to the actual repo
- Assume reader is technical but may not know this codebase
- Highlight complexity boundaries

---

# Special Handling

If repository is large:

- Provide summary first
- Offer deeper dive follow-up sections

If repository is small:

- Provide full walkthrough

If repo structure is unclear:

- State assumptions explicitly

---

# Optional Add-Ons

If user says “for interview prep”:

- Add likely interview questions
- Add how to explain design decisions clearly
- Add tradeoffs discussion

If user says “for onboarding”:

- Add a “Day 1 reading order”
- Add common mistakes new devs make

If user says “for refactor”:

- Add architectural weaknesses and cleanups
