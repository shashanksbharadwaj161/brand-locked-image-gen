#!/usr/bin/env python3
"""
Gau Bhoomi Naturals — Stage 2 Logo Compositor
=============================================
Composites the exact GBN logo PNG onto an AI-generated base scene.

Guarantees:
  - Pixel-perfect logo (no AI interpretation)
  - Aspect ratio always preserved (never stretched)
  - Subtle drop shadow behind logo
  - Optional cream backing strip for contrast
  - Logo readable at final output size

Usage:
    python3 gbn_composite.py BASE.png LOGO.png OUT.png --variant process
    python3 gbn_composite.py BASE.png LOGO.png OUT.png --variant hero   # no-op copy

Variants:
    hero       -> no logo (product label carries the brand)
    process    -> top center, 15% width, cream strip
    lifestyle  -> top center, 15% width, cream strip
    flatlay    -> top center, 15% width, transparent (gold logo on dark linen)
"""

import argparse
import sys
from PIL import Image, ImageFilter

# ---- Brand constants -------------------------------------------------------
CREAM = (251, 247, 239, 255)   # #FBF7EF
FOREST = (20, 42, 29, 255)     # #142A1D
GOLD = (201, 168, 76, 255)     # #C9A84C

# ---- Variant configuration -------------------------------------------------
VARIANTS = {
    "hero":      {"logo": False},
    "process":   {"logo": True, "width_pct": 0.15, "top_pct": 0.045, "backing": "cream"},
    "lifestyle": {"logo": True, "width_pct": 0.15, "top_pct": 0.045, "backing": "cream"},
    "flatlay":   {"logo": True, "width_pct": 0.15, "top_pct": 0.045, "backing": "none"},
}

# Minimum logo width in px to stay readable at final output size.
MIN_LOGO_W = 120


def trim_transparent(img: Image.Image) -> Image.Image:
    """Crop fully-transparent margins so the 15% sizing applies to real artwork."""
    if img.mode != "RGBA":
        return img
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def make_shadow(logo: Image.Image, blur: int, offset: int, opacity: int) -> Image.Image:
    """Build a soft drop shadow from the logo's alpha channel."""
    pad = blur * 3 + offset
    canvas = Image.new("RGBA", (logo.width + pad * 2, logo.height + pad * 2), (0, 0, 0, 0))

    # Silhouette from alpha, darkened and softened.
    silhouette = Image.new("RGBA", logo.size, (0, 0, 0, 0))
    silhouette.putalpha(logo.getchannel("A").point(lambda a: int(a * opacity / 255)))

    canvas.paste(silhouette, (pad + offset, pad + offset), silhouette)
    return canvas.filter(ImageFilter.GaussianBlur(blur)), pad


def add_backing_strip(base: Image.Image, box, style: str, radius_ratio=0.5):
    """Draw a soft cream strip behind the logo for contrast on busy scenes."""
    if style != "cream":
        return base

    from PIL import ImageDraw

    x0, y0, x1, y1 = box
    padx = int((x1 - x0) * 0.18)
    pady = int((y1 - y0) * 0.35)
    strip_box = (x0 - padx, y0 - pady, x1 + padx, y1 + pady)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    h = strip_box[3] - strip_box[1]
    draw.rounded_rectangle(strip_box, radius=int(h * radius_ratio), fill=CREAM)

    # Feather the strip edges slightly so it reads as designed, not pasted.
    layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    return Image.alpha_composite(base, layer)


def composite(base_path: str, logo_path: str, out_path: str, variant: str,
              width_pct=None, verbose=True) -> str:
    cfg = VARIANTS.get(variant)
    if cfg is None:
        raise ValueError(f"Unknown variant '{variant}'. Choose from {list(VARIANTS)}")

    base = Image.open(base_path).convert("RGBA")

    # Enforce square 1:1 output.
    if base.width != base.height:
        side = min(base.width, base.height)
        left = (base.width - side) // 2
        top = (base.height - side) // 2
        base = base.crop((left, top, left + side, top + side))
        if verbose:
            print(f"  ! base was not square -> center-cropped to {side}x{side}")

    # Hero: no logo, just normalize and save.
    if not cfg["logo"]:
        base.convert("RGB").save(out_path, "PNG")
        if verbose:
            print(f"  hero variant -> no logo applied. Saved {out_path}")
        return out_path

    logo = trim_transparent(Image.open(logo_path).convert("RGBA"))

    # Aspect ratio is measured on the TRIMMED artwork, since that is what we
    # actually scale. Comparing against the untrimmed file would falsely flag
    # drift whenever the source PNG has transparent margins.
    src_ar = logo.width / logo.height

    # --- Size: preserve aspect ratio, never stretch --------------------------
    pct = width_pct if width_pct is not None else cfg["width_pct"]
    target_w = int(base.width * pct)

    if target_w < MIN_LOGO_W:
        target_w = MIN_LOGO_W
        if verbose:
            print(f"  ! logo bumped to {MIN_LOGO_W}px min width for readability")

    scale = target_w / logo.width
    target_h = max(1, round(logo.height * scale))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    # Verify aspect ratio held through the resize (guards against stretching).
    new_ar = target_w / target_h
    assert abs(src_ar - new_ar) / src_ar < 0.02, (
        f"aspect ratio drift: {src_ar:.4f} -> {new_ar:.4f}")

    # --- Position: top center ------------------------------------------------
    x = (base.width - target_w) // 2
    y = int(base.height * cfg["top_pct"])

    # --- Backing strip -------------------------------------------------------
    base = add_backing_strip(base, (x, y, x + target_w, y + target_h), cfg["backing"])

    # --- Drop shadow ---------------------------------------------------------
    blur = max(2, int(target_h * 0.06))
    offset = max(1, int(target_h * 0.035))
    opacity = 90 if cfg["backing"] == "cream" else 130

    shadow, pad = make_shadow(logo, blur, offset, opacity)
    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_layer.paste(shadow, (x - pad, y - pad), shadow)
    base = Image.alpha_composite(base, shadow_layer)

    # --- Logo ----------------------------------------------------------------
    logo_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    logo_layer.paste(logo, (x, y), logo)
    base = Image.alpha_composite(base, logo_layer)

    base.convert("RGB").save(out_path, "PNG")

    if verbose:
        print(f"  variant   : {variant}")
        print(f"  canvas    : {base.width}x{base.height}")
        print(f"  logo size : {target_w}x{target_h}  ({pct*100:.0f}% width)")
        print(f"  position  : top-center at ({x}, {y})")
        print(f"  aspect    : {src_ar:.4f} -> {new_ar:.4f}  OK (preserved)")
        print(f"  backing   : {cfg['backing']}")
        print(f"  shadow    : blur={blur} offset={offset} opacity={opacity}")
        print(f"  saved     : {out_path}")

    return out_path


def main():
    p = argparse.ArgumentParser(description="GBN Stage 2 logo compositor")
    p.add_argument("base", help="AI-generated base scene PNG")
    p.add_argument("logo", help="Exact GBN logo PNG (transparent background)")
    p.add_argument("out", help="Output PNG path")
    p.add_argument("--variant", required=True, choices=list(VARIANTS))
    p.add_argument("--width-pct", type=float, default=None,
                   help="Override logo width as fraction of canvas, e.g. 0.15")
    a = p.parse_args()

    try:
        composite(a.base, a.logo, a.out, a.variant, a.width_pct)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
