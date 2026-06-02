#!/usr/bin/env python3
"""Copy ~/Desktop/FLUX (heic/png) into public/ — resize only if too wide."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SITE_ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = SITE_ROOT / "public" / "images" / "fluxion-hero.png"
OUT_WEBP = SITE_ROOT / "public" / "images" / "fluxion-hero.webp"
DESKTOP = Path.home() / "Desktop"
SOURCES = [
    DESKTOP / "FLUX.heic",
    DESKTOP / "FLUX.HEIC",
    DESKTOP / "FLUX.png",
    DESKTOP / "FLUX.PNG",
    DESKTOP / "screenshot_fluxion.png",
]


def pick_source() -> Path:
    for path in SOURCES:
        if path.is_file():
            return path
    names = ", ".join(p.name for p in SOURCES[:4])
    raise SystemExit(f"Missing Desktop capture (tried {names})")


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return opened.convert("RGB")


def resize_if_needed(image: Image.Image, max_width: int = 2800) -> Image.Image:
    if image.width <= max_width:
        return image
    height = round(image.height * max_width / image.width)
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def export_webp(image: Image.Image, webp_path: Path) -> None:
    image.save(webp_path, format="WEBP", quality=90, method=6)


def main() -> None:
    source = pick_source()
    if source.suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except Exception:
            raise SystemExit("Install pillow-heif to read HEIC (pnpm prepare:hero does this automatically)")
    image = resize_if_needed(load_image(source))

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT_PNG, optimize=True)
    export_webp(image, OUT_WEBP)

    print(f"source: {source}")
    print(f"output: {OUT_PNG} ({image.width}x{image.height})")
    print(f"APP_SCREENSHOT_WIDTH = {image.width}")
    print(f"APP_SCREENSHOT_HEIGHT = {image.height}")


if __name__ == "__main__":
    main()
