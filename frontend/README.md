# Origami launch site

The public site for Origami, exported statically and served from GitHub Pages at `/Origami`. It has two pages, a landing page and an FAQ, and it will never have a backend: no forms, no analytics, no accounts. That constraint is recorded in [`docs/ELECTRON_PORT_PLAN.md`](../docs/ELECTRON_PORT_PLAN.md) section 5.

## Development

```bash
bun install
bun run dev
```

The dev server serves the site under the `/Origami` base path, so open [http://localhost:3000/Origami](http://localhost:3000/Origami).

## Build

```bash
bun run build
```

`next build` writes the static export to `out/`. The `.github/workflows/deploy-pages.yml` workflow builds and deploys it on every push to `main` that touches `frontend/`.

## Constraints

- Static export only. No route handlers, no server actions, no rewrites.
- Light mode only.
- Motion respects `prefers-reduced-motion`.
- Fonts are self-hosted at build time through `next/font`. No runtime requests to third parties.
