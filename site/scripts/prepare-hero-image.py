#!/usr/bin/env python3
"""Copy ~/Desktop/screenshot_fluxion.png into public/ — resize only if too wide."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SITE_ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = SITE_ROOT / "public" / "images" / "fluxion-hero.png"
OUT_WEBP = SITE_ROOT / "public" / "images" / "fluxion-hero.webp"
SOURCE = Path.home() / "Desktop" / "screenshot_fluxion.png"


def resize_if_needed(image: Image.Image, max_width: int = 2800) -> Image.Image:
    if image.width <= max_width:
        return image
    height = round(image.height * max_width / image.width)
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def export_webp(image: Image.Image, webp_path: Path) -> None:
    image.save(webp_path, format="WEBP", quality=90, method=6)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing {SOURCE}")

    with Image.open(SOURCE) as opened:
        image = resize_if_needed(opened.convert("RGB"))

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT_PNG, optimize=True)
    export_webp(image, OUT_WEBP)

    print(f"source: {SOURCE}")
    print(f"output: {OUT_PNG} ({image.width}x{image.height})")
    print(f"APP_SCREENSHOT_WIDTH = {image.width}")
    print(f"APP_SCREENSHOT_HEIGHT = {image.height}")


if __name__ == "__main__":
    main()
