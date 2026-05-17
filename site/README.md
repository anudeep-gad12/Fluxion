# Fluxion.cc site

Static landing page for `fluxion.cc`, intended for Cloudflare Pages.

## Local development

```bash
pnpm install
pnpm dev
```

## Build

```bash
pnpm build
```

## Cloudflare Pages

- Project root: `site`
- Build command: `pnpm install --frozen-lockfile && pnpm build`
- Build output directory: `dist`

## Screenshot placeholders

Drop final screenshots into `public/images/` with these names:

- `hero-app.png`
- `model-picker.png`
- `agent-run.png`
- `workspace-diff.png`
- `local-history.png`
- `og.png`
