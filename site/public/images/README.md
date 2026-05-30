# Fluxion landing illustrations

Product-style SVG illustrations (desktop tokens: `#09090b`, `#79e6ff`) used by `site/src/main.tsx`:

| File | Use |
|------|-----|
| `hero-app.svg` | Hero + repo-work sections |
| `model-picker.svg` | Model freedom split section |
| `terminal-panel.svg` | Integrated terminal section |
| `og.svg` | Source for social preview |
| `og.png` | Open Graph / Twitter card (1200×630, generated from `og.svg`) |

Legacy PNGs (`hero-app.png`, `model-picker.png`) remain for reference; the site prefers SVG.

Regenerate `og.png` after editing `og.svg`:

```bash
qlmanage -t -s 1200 -o site/public/images site/public/images/og.svg
mv site/public/images/og.svg.png site/public/images/og.png
sips -c 630 1200 site/public/images/og.png
```
