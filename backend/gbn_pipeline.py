#!/usr/bin/env python3
"""
Gau Bhoomi Naturals — Brand Image Pipeline
==========================================
Stage 1  Generate 4 base scenes per product via the HuggingFace Inference API
Stage 2  Composite the exact GBN logo PNG onto posters 2-4 with Pillow

The logo is NEVER described to the model. It is placed programmatically, so
it is pixel-identical on every asset.

Single product:
    export HF_TOKEN=hf_xxx
    python gbn_pipeline.py --product "A2 Gir Cow Ghee Bilona" \
        --size "500ml" --category "Ghee" --logo logo.png

Batch:
    python gbn_pipeline.py --batch products.csv --logo logo.png

Offline check (no API calls, validates prompts + compositing + layout):
    python gbn_pipeline.py --batch products.csv --logo logo.png --dry-run
"""

import argparse
import csv
import io
import os
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

from gbn_prompts import generate_product_prompts, audit_uniqueness
from gbn_composite import composite

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PRIMARY_MODEL = "black-forest-labs/FLUX.1-dev"
FALLBACK_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
API_ROOT = "https://api-inference.huggingface.co/models/"

MAX_RETRIES = 3
RETRY_BACKOFF = 8       # seconds, multiplied by attempt number
REQUEST_TIMEOUT = 180
MIN_DIMENSION = 512     # reject anything smaller and retry
LOGO_WIDTH_PCT = 0.22   # 22% — sized so the wordmark stays readable

SLOT_ORDER = ["01_Hero", "02_Process", "03_Lifestyle", "04_FlatLay"]
SLOT_LABEL = {
    "01_Hero": "Hero shot",
    "02_Process": "Process poster",
    "03_Lifestyle": "Lifestyle poster",
    "04_FlatLay": "Flat lay poster",
}


class GenerationError(Exception):
    pass


# ---------------------------------------------------------------------------
# Stage 1 — HuggingFace Inference API
# ---------------------------------------------------------------------------
class HFGenerator:
    def __init__(self, token: str, model: str = PRIMARY_MODEL,
                 fallback: str = FALLBACK_MODEL, dry_run: bool = False):
        if not dry_run and not token:
            raise ValueError(
                "HF_TOKEN missing. Set it in the environment or pass "
                "--hf-token. Never hardcode it into a file.")
        self.token = token
        self.model = model
        self.fallback = fallback
        self.dry_run = dry_run
        self.session = requests.Session()

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "image/png"}

    def _call(self, model: str, prompt: str, negative: str) -> Image.Image:
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative,
                "guidance_scale": 7.0,
                "num_inference_steps": 30,
                "width": 1024,
                "height": 1024,
            },
            "options": {"wait_for_model": True},
        }
        r = self.session.post(API_ROOT + model, headers=self._headers(),
                              json=payload, timeout=REQUEST_TIMEOUT)

        if r.status_code == 503:
            raise GenerationError("model loading (503)")
        if r.status_code == 429:
            raise GenerationError("rate limited (429)")
        if r.status_code == 401:
            raise GenerationError("bad or revoked HF_TOKEN (401)")
        if r.status_code != 200:
            raise GenerationError(f"HTTP {r.status_code}: {r.text[:200]}")

        ctype = r.headers.get("content-type", "")
        if "image" not in ctype:
            raise GenerationError(f"non-image response ({ctype}): {r.text[:200]}")

        return Image.open(io.BytesIO(r.content)).convert("RGB")

    def _placeholder(self, prompt: str) -> Image.Image:
        """Offline stand-in so the pipeline can be validated without the API."""
        from PIL import ImageDraw
        img = Image.new("RGB", (1024, 1024), (20, 42, 29))
        d = ImageDraw.Draw(img)
        d.rectangle((40, 40, 984, 984), outline=(201, 168, 76), width=3)
        words, line, y = prompt.split(), "", 300
        for w in words[:60]:
            if len(line) + len(w) > 46:
                d.text((70, y), line, fill=(251, 247, 239)); y += 26; line = ""
            line += w + " "
        d.text((70, y), line, fill=(251, 247, 239))
        d.text((70, 120), "DRY RUN PLACEHOLDER", fill=(201, 168, 76))
        return img

    def generate(self, prompt: str, negative: str, label: str) -> Image.Image:
        if self.dry_run:
            return self._placeholder(prompt)

        models = [self.model, self.fallback]
        last = None

        for model in models:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    img = self._call(model, prompt, negative)

                    if img.width < MIN_DIMENSION or img.height < MIN_DIMENSION:
                        raise GenerationError(
                            f"undersized {img.width}x{img.height}, "
                            f"minimum is {MIN_DIMENSION}")

                    if model != self.model:
                        print(f"      (produced by fallback model {model})")
                    return img

                except (GenerationError, requests.RequestException) as e:
                    last = e
                    if attempt < MAX_RETRIES:
                        wait = RETRY_BACKOFF * attempt
                        print(f"      retry {attempt}/{MAX_RETRIES - 1} for "
                              f"{label} — {e} — waiting {wait}s")
                        time.sleep(wait)
                    else:
                        print(f"      {model} exhausted after {MAX_RETRIES} "
                              f"attempts: {e}")

            if model != models[-1]:
                print(f"      falling back to {self.fallback}")

        raise GenerationError(f"all models failed for {label}: {last}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip()
    return re.sub(r"[\s-]+", "_", s)


def process_product(gen: HFGenerator, product: str, size: str, category: str,
                    logo: Path, out_root: Path, keep_base: bool = False) -> dict:
    prompts = generate_product_prompts(product, size, category)

    out_dir = out_root / slugify(category) / f"{slugify(product)}_{slugify(size)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    print(f"\n{'='*66}\n{product} — {size}  [{category}]\n{'='*66}")

    for i, slot in enumerate(SLOT_ORDER, start=1):
        spec = prompts[slot]
        label = SLOT_LABEL[slot]
        print(f"  [{i}/4] Generating {label} for {product}...")

        final_path = out_dir / f"{slot}.png"

        try:
            img = gen.generate(spec["prompt"], spec["negative"], label)
        except GenerationError as e:
            print(f"  [{i}/4] FAILED {label}: {e}")
            results[slot] = f"FAILED — {e}"
            continue

        base_path = out_dir / f".base_{slot}.png"
        img.save(base_path, "PNG")

        # Stage 2 — logo compositing
        composite(str(base_path), str(logo), str(final_path),
                  spec["variant"], width_pct=LOGO_WIDTH_PCT, verbose=False)

        if not keep_base:
            # Cleanup is best-effort: read-only mounts and locked files must
            # never fail an otherwise successful generation.
            try:
                base_path.unlink(missing_ok=True)
            except OSError:
                pass

        with Image.open(final_path) as f:
            dims = f"{f.width}x{f.height}"

        logo_note = "no logo (by design)" if spec["variant"] == "hero" \
            else f"logo {int(LOGO_WIDTH_PCT*100)}% top-center"
        print(f"  [{i}/4] Saved {slot}.png  ({dims}, {logo_note})")
        results[slot] = "OK"

    ok = sum(1 for v in results.values() if v == "OK")
    if ok == 4:
        print(f"\n  [OK] {product} {size} — all 4 images saved -> {out_dir}")
    else:
        print(f"\n  [PARTIAL] {product} {size} — {ok}/4 succeeded -> {out_dir}")

    return results


def read_batch(path: Path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            clean = {k.strip().lower(): (v or "").strip()
                     for k, v in row.items() if k}
            if not clean.get("product_name"):
                continue
            rows.append((clean["product_name"], clean.get("size", ""),
                         clean.get("category", "Uncategorised")))
    return rows


def main():
    p = argparse.ArgumentParser(
        description="Gau Bhoomi Naturals brand image pipeline")
    p.add_argument("--product")
    p.add_argument("--size")
    p.add_argument("--category")
    p.add_argument("--batch", help="CSV: product_name,size,category")
    p.add_argument("--logo", required=True, help="Exact GBN logo PNG")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN", ""))
    p.add_argument("--out", default="gbn_output")
    p.add_argument("--model", default=PRIMARY_MODEL)
    p.add_argument("--dry-run", action="store_true",
                   help="Skip the API; validate prompts, layout and compositing")
    p.add_argument("--keep-base", action="store_true",
                   help="Keep pre-logo base scenes for inspection")
    a = p.parse_args()

    if not a.batch and not a.product:
        p.error("provide --product or --batch")

    logo = Path(a.logo)
    if not logo.exists():
        p.error(f"logo not found: {logo}")

    issues = audit_uniqueness()
    if issues:
        print("Uniqueness audit found problems:")
        for i in issues:
            print("  -", i)
        print()
    else:
        print("Uniqueness audit: PASS — every product concept is distinct.\n")

    try:
        gen = HFGenerator(a.hf_token, a.model, FALLBACK_MODEL, a.dry_run)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    if a.dry_run:
        print("*** DRY RUN — no API calls, placeholder scenes ***\n")

    jobs = read_batch(Path(a.batch)) if a.batch else \
        [(a.product, a.size or "", a.category or "Uncategorised")]

    out_root = Path(a.out)
    total_ok = 0

    for product, size, category in jobs:
        try:
            res = process_product(gen, product, size, category, logo,
                                  out_root, a.keep_base)
            total_ok += sum(1 for v in res.values() if v == "OK")
        except ValueError as e:
            print(f"\n  [SKIP] {product}: {e}")

    print(f"\n{'='*66}")
    print(f"Batch complete — {len(jobs)} product(s), "
          f"{total_ok}/{len(jobs)*4} images generated")
    print(f"Output: {out_root.resolve()}")


if __name__ == "__main__":
    main()
