# Fluxion brand assets

**Source of truth:** [`../macos/Fluxion.svg`](../macos/Fluxion.svg) — the macOS app icon mark (`~>` on dark squircle).

## Updating the logo

1. Edit `assets/macos/Fluxion.svg`.
2. Run `./scripts/sync_brand_assets.sh` to copy SVG favicons into `ui/` and `site/`.
3. Regenerate Tauri platform icons:

   ```bash
   cd src-tauri && cargo tauri icon ../assets/macos/Fluxion.svg
   ```

4. Re-run `./scripts/sync_brand_assets.sh` so PNG exports pick up new raster sizes.

## Where the mark is used

| Asset | Consumers |
| ----- | --------- |
| `Fluxion.svg` | Tauri `icon.icns`, sync script |
| `ui/public/favicon.svg` | Desktop sidebar, web sidebar, browser tab |
| `site/public/favicon.svg` | fluxion.cc favicon |
| `site/public/logo-*.png` | Landing nav/footer (from Tauri PNG exports) |
| `site/public/images/*.png` | Landing illustrations (product marketing) |
