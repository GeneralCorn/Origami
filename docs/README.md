# Documentation

Two kinds of document live here. The **specs** are the authority on what gets built and why, and are meant to be edited as decisions change. The **research** under `research/` is a dated snapshot of what was true when it was written, and should be corrected rather than quietly rewritten when it turns out to be wrong.

Start with [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md) for what this is for, then [STATUS.md](STATUS.md) for where it actually is, what is blocked, and what to pick up next.

## Specs

| Document | What it decides |
|---|---|
| [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md) | What the product is, which framings were rejected and why, the constraints that are not negotiable, and what retention actually costs. Read before proposing a direction. |
| [ELECTRON_PORT_PLAN.md](ELECTRON_PORT_PLAN.md) | The desktop port: the five architectural decisions, the phase sequence, and the open questions. The closest thing to a roadmap. |
| [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) | The Item and Segment model, the provenance and taint rule, and the migration order. Section 3 is load-bearing and should be read before any connector work. |
| [INTEGRATIONS_RESEARCH.md](INTEGRATIONS_RESEARCH.md) | Every candidate data source, with a ship, opt-in, or never verdict and the reason. Section 4 covers the macOS permission model, where a missing declaration fails silently. |
| [COST_MODEL.md](COST_MODEL.md) | Where the money goes and the four levers against it. Section 3 is the lever list. |
| [EDITOR_DECISION.md](EDITOR_DECISION.md) | Resolves the CodeMirror 6 question with a measured spike. Read before starting the editor work. |
| [INTERFACE_DIRECTIONS.md](INTERFACE_DIRECTIONS.md) | Three directions for the desktop interface, with the bundle, image and compositing measurements behind them. Settles glassmorphism, neumorphism and macOS vibrancy, and surveys the component libraries. |
| [MODEL_STRATEGY.md](MODEL_STRATEGY.md) | Which call sites can leave the Anthropic API and which cannot, why the saving is smaller than it looks, and the migration order. Read before changing anything about models. |

## Research

Dated snapshots. Each is tagged `[VERIFIED]`, `[SECONDARY]`, or `[UNVERIFIED]` in the same way the specs are, and each carries its own sources.

| Document | Subject |
|---|---|
| [user-sentiment-2026-07.md](research/user-sentiment-2026-07.md) | What people actually want and fear in personal AI tools, and why they abandon them. |
| [competitive-landscape-2026-07.md](research/competitive-landscape-2026-07.md) | Products, the ones that died and why, relevant papers, and a gap analysis. |
| [mcp-api-streaming-2026-07.md](research/mcp-api-streaming-2026-07.md) | MCP in both directions, the streaming transport decision, and what needs user credentials. |
| [adversarial-review-2026-07.md](research/adversarial-review-2026-07.md) | An attack on the other three. It overturns two claims and corrects several numbers, so read it alongside them rather than after. |

## Conventions

Claims carry a confidence tag:

- `[VERIFIED]` means it was checked against a primary source or measured directly, and the evidence is cited.
- `[SECONDARY]` means it rests on a summary, a vendor's own page, or a single uncorroborated report.
- `[UNVERIFIED]` means it is an assumption that has not been tested, and the document says what would settle it.

The tags are not decoration. The adversarial review found that an unlabelled statistic repeated from a news article contradicted its own primary source, and that a vendor's marketing page was the origin of an effort estimate that a decision then rested on. When a claim changes status, say so in the document rather than editing it silently.
