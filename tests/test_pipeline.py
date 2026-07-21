#!/usr/bin/env python3
"""
Self-contained pipeline tests (no API calls, no network).

Run from the repo root:
    python tests/test_pipeline.py

Exercises prompt generation, the uniqueness audit, brand-name threading,
logo compositing, and the full dry-run SSE event stream (single, batch,
custom, raw, retry, and error paths).
"""
import base64
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw  # noqa: E402

import gbn_prompts as gp  # noqa: E402
from orchestrator import run_jobs, SLOTS  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        FAILURES.append(msg)


def make_logo() -> str:
    """A transparent PNG with real artwork inside transparent margins."""
    img = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((120, 90, 480, 210), radius=20, fill=(201, 168, 76, 255))
    d.ellipse((260, 120, 340, 180), fill=(20, 42, 29, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


LOGO = make_logo()


def decode(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def gold_in_top_band(img):
    band = img.crop((312, 40, 712, 230))          # RGB -> 3 bytes per pixel
    px = band.tobytes()
    gold = 0
    for i in range(0, len(px), 3):
        if px[i] > 150 and px[i + 1] > 110 and px[i + 2] < 120:
            gold += 1
    return gold


def test_prompt_engine():
    print("== prompt engine ==")
    check(len(gp.PROFILES) == 11, "11 profiles loaded")
    check(not gp.audit_uniqueness(), "uniqueness audit passes")
    p = gp.generate_product_prompts("A2 Gir Cow Ghee Bilona", "500ml", "Ghee")
    check(set(p) == {s[0] for s in SLOTS}, "four slots produced")
    check("'Gau Bhoomi Naturals'" in p["01_Hero"]["prompt"], "default brand in hero")
    p2 = gp.generate_product_prompts("Organic Coconut Oil Khopra Cold Pressed",
                                     "500 ML", "Oil", brand_name="Acme")
    check("'Acme'" in p2["01_Hero"]["prompt"], "custom brand threaded to hero")
    check("Gau Bhoomi" not in p2["02_Process"]["prompt"], "no GBN leak with custom brand")


def test_single_dry_run():
    print("== single product dry-run ==")
    evs = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                        logo_base64=LOGO, brand_name="Gau Bhoomi Naturals",
                        jobs=[("A2 Gir Cow Ghee Bilona", "500ml", "Ghee")]))
    check(evs[0]["type"] == "audit", "first event is audit")
    imgs = [e for e in evs if e["type"] == "image"]
    check(len(imgs) == 4, "four images produced")
    for e in imgs:
        im = decode(e["data"])
        check(im.size == (1024, 1024), f"{e['slot']} is 1024x1024")
    hero = next(e for e in imgs if e["slot"] == "01_Hero")
    proc = next(e for e in imgs if e["slot"] == "02_Process")
    check(gold_in_top_band(decode(hero["data"])) < 400, "hero has no logo")
    check(gold_in_top_band(decode(proc["data"])) > 400, "process has composited logo")
    comp = [e for e in evs if e["type"] == "complete"][-1]
    check(comp["total_ok"] == 4, "complete reports 4 ok")


def test_batch():
    print("== batch of two ==")
    evs = list(run_jobs(provider="together", api_key="", dry_run=True,
                        logo_base64=LOGO, brand_name="Acme",
                        jobs=[("Organic Coconut Oil Khopra Cold Pressed", "500 ML", "Oil"),
                              ("Organic Almond Oil Cold Pressed", "500 ML", "Oil")]))
    imgs = [e for e in evs if e["type"] == "image"]
    check(len(imgs) == 8, "eight images across two products")
    check(sorted({e["index"] for e in imgs}) == [0, 1], "two product indices")


def test_custom_and_raw():
    print("== custom + raw prompt paths ==")
    custom = {"hero": "a glass bottle on marble", "process": "a mill scene",
              "lifestyle": "hands cooking", "flatlay": "overhead ingredients"}
    evs = list(run_jobs(provider="stability", api_key="", dry_run=True,
                        logo_base64=LOGO, brand_name="MyBrand",
                        jobs=[("Anything", "250 ML", "Other")],
                        custom_prompts=custom))
    pe = [e for e in evs if e["type"] == "prompts"][0]
    check("marble" in pe["prompts"]["01_Hero"]["prompt"], "custom hero used")
    check("clean and empty" in pe["prompts"]["02_Process"]["prompt"],
          "top-clean directive appended to custom poster")

    raw = {"01_Hero": "VERBATIM HERO", "02_Process": "P2",
           "03_Lifestyle": "P3", "04_FlatLay": "P4"}
    evs2 = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                         logo_base64=LOGO, brand_name="X",
                         jobs=[("A2 Gir Cow Ghee Bilona", "500ml", "Ghee")],
                         raw_prompts=raw))
    pe2 = [e for e in evs2 if e["type"] == "prompts"][0]
    check(pe2["prompts"]["01_Hero"]["prompt"] == "VERBATIM HERO", "raw used verbatim")


def test_retry_and_errors():
    print("== retry (only_slots) + error paths ==")
    evs = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                        logo_base64=LOGO, brand_name="X",
                        jobs=[("A2 Gir Cow Ghee Bilona", "500ml", "Ghee")],
                        only_slots=["03_Lifestyle"]))
    imgs = [e for e in evs if e["type"] == "image"]
    check(len(imgs) == 1 and imgs[0]["slot"] == "03_Lifestyle", "retry regenerates one slot")

    # A product with no curated profile now succeeds via the universal
    # fallback engine instead of erroring out — "any product" is the point.
    evs2 = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                         logo_base64=LOGO, brand_name="X",
                         jobs=[("Unknown Product ZZZ", "1 L", "Other")]))
    imgs2 = [e for e in evs2 if e["type"] == "image"]
    check(len(imgs2) == 4, "unmatched product still produces 4 images via generic engine")
    pe = [e for e in evs2 if e["type"] == "prompts"][0]
    check(pe["source"] == "generic", "prompts event reports source=generic")

    # Blank product name is the one input that still fails cleanly.
    evs2b = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                          logo_base64=LOGO, brand_name="X",
                          jobs=[("   ", "1 L", "Other")]))
    errs = [e for e in evs2b if e["type"] == "error"]
    check(len(errs) == 4, "blank product name -> 4 slot errors, batch continues")

    evs3 = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                         logo_base64="", brand_name="X",
                         jobs=[("A2 Gir Cow Ghee Bilona", "500ml", "Ghee")]))
    check(any(e["type"] == "fatal" for e in evs3), "missing logo -> fatal")


def test_universal_fallback_any_product_any_brand():
    print("== universal fallback: any product, any brand, every family ==")
    cases = [
        ("Bluetooth Wireless Speaker", "1 unit", "Electronics", "SonicWave"),
        ("Organic Cotton Hoodie", "Large", "Apparel", "Northfield"),
        ("Vitamin C Face Serum", "30ml", "Skincare", "Lumina"),
        ("Himalayan Pink Salt", "500g", "Grocery", "PureEarth"),
        ("Quantum Flux Capacitor XJ-9", "1 unit", "", "Acme"),
    ]
    for name, size, category, brand in cases:
        evs = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                            logo_base64=LOGO, brand_name=brand,
                            jobs=[(name, size, category)]))
        imgs = [e for e in evs if e["type"] == "image"]
        check(len(imgs) == 4, f"{name} ({category or 'no category'}) -> 4 images")
        hero = decode(next(e for e in imgs if e["slot"] == "01_Hero")["data"])
        proc = decode(next(e for e in imgs if e["slot"] == "02_Process")["data"])
        check(gold_in_top_band(hero) < 400, f"{name}: hero has no logo")
        check(gold_in_top_band(proc) > 400, f"{name}: process has composited logo")
        pe = [e for e in evs if e["type"] == "prompts"][0]
        check(pe["source"] == "generic", f"{name}: source reported as generic")
        check(brand in pe["prompts"]["01_Hero"]["prompt"],
              f"{name}: brand name '{brand}' present in hero prompt")

    # Determinism across two independent runs of the same product/brand.
    def hero_prompt_for(name, brand):
        evs = list(run_jobs(provider="huggingface", api_key="", dry_run=True,
                            logo_base64=LOGO, brand_name=brand,
                            jobs=[(name, "1 unit", "Electronics")]))
        pe = [e for e in evs if e["type"] == "prompts"][0]
        return pe["prompts"]["01_Hero"]["prompt"]

    a = hero_prompt_for("Noise Cancelling Headphones", "AudioMax")
    b = hero_prompt_for("Noise Cancelling Headphones", "AudioMax")
    check(a == b, "same product+brand -> identical generic prompt (deterministic)")


if __name__ == "__main__":
    test_prompt_engine()
    test_single_dry_run()
    test_batch()
    test_custom_and_raw()
    test_retry_and_errors()
    test_universal_fallback_any_product_any_brand()
    print("\n" + ("ALL PASSED" if not FAILURES else f"{len(FAILURES)} FAILURE(S)"))
    sys.exit(1 if FAILURES else 0)
