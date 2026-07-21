#!/usr/bin/env python3
"""
Generation orchestrator
========================
Turns a generation request into a stream of JSON events (consumed as SSE by
the frontend). Owns the retry / model-fallback / minimum-size policy so that
"retrying…" and "falling back…" notices reach the browser live, and owns the
temp-file logo handling (decode → composite → base64 → delete).

Event contract (every event is a JSON object with a ``type``):

  {"type":"audit","passed":bool,"issues":[...]}
  {"type":"batch_start","total_products":N,"total_images":N*4}
  {"type":"product_start","index":i,"total":N,"product":..,"size":..,"category":..}
  {"type":"prompts","index":i,"prompts":{slot:{prompt,negative,variant}}}
  {"type":"progress","index":i,"slot":..,"label":..,"message":..,"attempt":k}
  {"type":"image","index":i,"slot":..,"label":..,"variant":..,"data":<b64>,"status":"ok"}
  {"type":"error","index":i,"slot":..,"label":..,"message":..}
  {"type":"product_complete","index":i,"product":..,"ok":k,"total":4}
  {"type":"complete","total_ok":M,"total":N*4}
  {"type":"fatal","message":..}      # unrecoverable; stream ends

The generator cleans up all temp files in a ``finally`` block, so a cancelled
request (client disconnect) never leaks the caller's logo to disk.
"""

from __future__ import annotations

import base64
import binascii
import io
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from PIL import Image

import gbn_prompts as gp
from gbn_composite import composite
from generators import (
    MAX_RETRIES,
    MIN_DIMENSION,
    RETRY_BACKOFF,
    FatalGenerationError,
    GenerationError,
    make_generator,
)

# 22% width, top-center — sized so a wordmark stays readable at 1024px
# (quality rule #5). Hero gets no logo.
LOGO_WIDTH_PCT = 0.22

# slot key, human label, compositor variant, custom-prompt field name
SLOTS: List[Tuple[str, str, str, str]] = [
    ("01_Hero", "Hero shot", "hero", "hero"),
    ("02_Process", "Process poster", "process", "process"),
    ("03_Lifestyle", "Lifestyle poster", "lifestyle", "lifestyle"),
    ("04_FlatLay", "Flat lay poster", "flatlay", "flatlay"),
]

_NEG_BY_VARIANT = {
    "hero": gp.NEG_HERO,
    "process": gp.NEG_POSTER,
    "lifestyle": gp.NEG_POSTER,
    "flatlay": gp.NEG_FLAT,
}


# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------
def preview_prompts(product_name: str, size: str, category: str,
                    brand_name: str = gp.DEFAULT_BRAND_NAME
                    ) -> Tuple[Dict[str, Dict], str]:
    """The 4 auto prompts for one SKU, for ANY product name.

    Returns (prompts, source) where source is "curated" (one of the 11
    hand-tuned GBN profiles matched) or "generic" (the universal fallback
    engine built a coherent prompt set on the fly). Raises ValueError only
    if product_name is blank.
    """
    return gp.generate_any_product_prompts(product_name, size, category,
                                           brand_name)


def _decorate_custom(text: str, variant: str) -> str:
    text = (text or "").strip()
    extra = f" {gp.QUALITY}."
    if variant != "hero":
        extra += (" Leave the top 15 percent of the image clean and empty for "
                  "a logo, with no text or objects in that band.")
    return text + extra


def _resolve_slots(product: str, size: str, category: str, brand_name: str,
                   custom_prompts: Optional[Dict],
                   custom_negatives: Optional[Dict],
                   raw_prompts: Optional[Dict] = None
                   ) -> Tuple[List[Dict], str]:
    """Return (slots, source) — an ordered list of
    {slot,label,variant,prompt,negative}, plus where the prompts came from
    ("raw", "custom", "curated", or "generic").

    Priority: ``raw_prompts`` (used verbatim — the user edited the previewed
    auto prompts) > ``custom_prompts`` (Mode B, brand rules appended) > auto
    (curated profile if one matches, otherwise the universal generic engine
    — this always succeeds for any product name; it only raises ValueError
    if the product name itself is blank).
    """
    if raw_prompts:
        slots = []
        for slot, label, variant, _field in SLOTS:
            raw = (raw_prompts.get(slot) or "").strip()
            if not raw:
                raise FatalGenerationError(
                    f"Edited prompt for '{label}' is empty.")
            neg = ""
            if custom_negatives:
                neg = (custom_negatives.get(slot)
                       or custom_negatives.get(_field) or "").strip()
            slots.append({
                "slot": slot, "label": label, "variant": variant,
                "prompt": raw, "negative": neg or _NEG_BY_VARIANT[variant],
            })
        return slots, "raw"

    if custom_prompts:
        slots = []
        for slot, label, variant, field in SLOTS:
            raw = (custom_prompts.get(field) or "").strip()
            if not raw:
                raise FatalGenerationError(
                    f"Custom prompt for '{label}' is empty — fill in all four "
                    f"slots or switch to Auto Prompts.")
            neg = ""
            if custom_negatives:
                neg = (custom_negatives.get(field) or "").strip()
            if not neg:
                neg = _NEG_BY_VARIANT[variant]
            slots.append({
                "slot": slot, "label": label, "variant": variant,
                "prompt": _decorate_custom(raw, variant), "negative": neg,
            })
        return slots, "custom"

    auto, source = gp.generate_any_product_prompts(product, size, category,
                                                    brand_name)
    slots = []
    for slot, label, variant, _field in SLOTS:
        spec = auto[slot]
        slots.append({
            "slot": slot, "label": label, "variant": variant,
            "prompt": spec["prompt"], "negative": spec["negative"],
        })
    return slots, source


# ---------------------------------------------------------------------------
# Logo handling
# ---------------------------------------------------------------------------
def _decode_logo(logo_base64: str, dest: Path) -> Path:
    """Decode the browser-supplied logo to a unique temp PNG. Raises on bad
    input so the caller can report a clean fatal error."""
    if not logo_base64:
        raise FatalGenerationError(
            "No logo provided. Upload and lock a logo before generating.")
    raw = logo_base64.strip()
    if raw.startswith("data:"):
        # strip a data URL prefix like "data:image/png;base64,"
        comma = raw.find(",")
        if comma != -1:
            raw = raw[comma + 1:]
    try:
        blob = base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError) as e:
        raise FatalGenerationError(f"Logo is not valid base64: {e}")
    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception as e:  # noqa: BLE001 - surface the real Pillow reason
        raise FatalGenerationError(f"Logo is not a readable image: {e}")
    out = dest / "brand_logo.png"
    # Normalise to RGBA PNG so the compositor's alpha trim always has a channel.
    img.convert("RGBA").save(out, "PNG")
    return out


# ---------------------------------------------------------------------------
# Single-image generation (a sub-generator: yields events, returns the Image)
# ---------------------------------------------------------------------------
def _generate_image(gen, spec: Dict, brand_name: str, index: int
                    ) -> Iterator[Dict]:
    """Yield progress events for one image; return the PIL Image via
    StopIteration.value. Raises FatalGenerationError to abort the whole job,
    or GenerationError when every attempt is exhausted."""
    slot, label, variant = spec["slot"], spec["label"], spec["variant"]

    def prog(message, attempt=None):
        return {"type": "progress", "index": index, "slot": slot,
                "label": label, "message": message, "attempt": attempt}

    if gen.dry_run:
        yield prog("Rendering dry-run placeholder…", 1)
        return gen.placeholder(spec["prompt"], label, brand_name, slot)

    negative = spec["negative"] if gen.supports_negative else ""
    last: Optional[Exception] = None

    for mi, model in enumerate(gen.models):
        for attempt in range(1, MAX_RETRIES + 1):
            note = "" if mi == 0 else f" via {model}"
            yield prog(f"Generating {label}{note}…", attempt)
            try:
                seed = gen._seed() if gen.supports_seed else None
                img = gen.try_once(spec["prompt"], negative, model, seed)
                if img.width < MIN_DIMENSION or img.height < MIN_DIMENSION:
                    raise GenerationError(
                        f"image too small ({img.width}x{img.height}, need "
                        f"≥{MIN_DIMENSION})")
                return img
            except FatalGenerationError:
                raise
            except GenerationError as e:
                last = e
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF * attempt
                    yield prog(f"{e} — retrying {label} "
                               f"(attempt {attempt + 1}/{MAX_RETRIES}) in "
                               f"{wait}s…", attempt + 1)
                    time.sleep(wait)
                else:
                    yield prog(f"{model} exhausted after {MAX_RETRIES} "
                               f"attempts: {e}", attempt)
        if mi < len(gen.models) - 1:
            yield prog(f"Falling back to {gen.models[mi + 1]}…")

    raise GenerationError(f"all attempts failed: {last}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_jobs(*, provider: str, api_key: str, dry_run: bool,
             logo_base64: str, brand_name: str,
             jobs: List[Tuple[str, str, str]],
             custom_prompts: Optional[Dict] = None,
             custom_negatives: Optional[Dict] = None,
             raw_prompts: Optional[Dict] = None,
             only_slots: Optional[List[str]] = None) -> Iterator[Dict]:
    """Stream every event for a whole generation request (1..N products).

    ``only_slots`` restricts generation to a subset of slot keys (used by the
    single-image "Retry" button so a failed slot regenerates on its own).
    """
    brand_name = (brand_name or gp.DEFAULT_BRAND_NAME).strip() \
        or gp.DEFAULT_BRAND_NAME

    wanted = set(only_slots) if only_slots else None
    effective_slots = [s for s in SLOTS if wanted is None or s[0] in wanted]

    # Uniqueness audit up front (quality rule #6).
    issues = gp.audit_uniqueness()
    yield {"type": "audit", "passed": not issues, "issues": issues}

    if not jobs or not effective_slots:
        yield {"type": "fatal", "message": "No products to generate."}
        return

    tmp = Path(tempfile.mkdtemp(prefix="brandgen_"))
    try:
        # Build the generator (bad key / unknown provider -> fatal).
        try:
            gen = make_generator(provider, api_key, dry_run)
        except FatalGenerationError as e:
            yield {"type": "fatal", "message": str(e)}
            return

        # Decode the logo once for the whole request.
        try:
            logo_path = _decode_logo(logo_base64, tmp)
        except FatalGenerationError as e:
            yield {"type": "fatal", "message": str(e)}
            return

        total = len(jobs)
        yield {"type": "batch_start", "total_products": total,
               "total_images": total * len(effective_slots)}

        total_ok = 0
        for index, (product, size, category) in enumerate(jobs):
            yield {"type": "product_start", "index": index, "total": total,
                   "product": product, "size": size, "category": category}

            # Resolve prompts for this product. The universal fallback engine
            # means this succeeds for any product name in any category — the
            # ValueError path below is now only reachable for a blank name.
            try:
                slots, source = _resolve_slots(
                    product, size, category, brand_name,
                    custom_prompts if total == 1 else None,
                    custom_negatives if total == 1 else None,
                    raw_prompts if total == 1 else None)
            except FatalGenerationError as e:
                # e.g. an empty custom slot — this is a request error, stop.
                yield {"type": "fatal", "message": str(e)}
                return
            except ValueError as e:
                # Blank product name: report and skip this product.
                for slot, label, _v, _f in effective_slots:
                    yield {"type": "error", "index": index, "slot": slot,
                           "label": label, "message": str(e)}
                yield {"type": "product_complete", "index": index,
                       "product": product, "ok": 0,
                       "total": len(effective_slots)}
                continue

            if wanted is not None:
                slots = [s for s in slots if s["slot"] in wanted]

            yield {"type": "prompts", "index": index, "source": source,
                   "prompts": {s["slot"]: {"prompt": s["prompt"],
                                           "negative": s["negative"],
                                           "variant": s["variant"]}
                               for s in slots}}

            ok = 0
            for spec in slots:
                slot, label, variant = spec["slot"], spec["label"], spec["variant"]
                try:
                    # Drive the sub-generator, forwarding its progress events
                    # and capturing the returned image.
                    it = _generate_image(gen, spec, brand_name, index)
                    img: Optional[Image.Image] = None
                    try:
                        while True:
                            yield next(it)
                    except StopIteration as stop:
                        img = stop.value
                except FatalGenerationError as e:
                    yield {"type": "fatal", "message": str(e)}
                    return
                except GenerationError as e:
                    yield {"type": "error", "index": index, "slot": slot,
                           "label": label, "message": str(e)}
                    continue

                # Stage 2 — composite the locked logo (hero is a no-op copy).
                try:
                    b64 = _composite_to_b64(img, logo_path, variant, tmp,
                                            index, slot)
                except Exception as e:  # noqa: BLE001 - never kill the batch
                    yield {"type": "error", "index": index, "slot": slot,
                           "label": label,
                           "message": f"logo compositing failed: {e}"}
                    continue

                ok += 1
                total_ok += 1
                yield {"type": "image", "index": index, "slot": slot,
                       "label": label, "variant": variant, "data": b64,
                       "status": "ok"}

            yield {"type": "product_complete", "index": index,
                   "product": product, "ok": ok, "total": len(effective_slots)}

        yield {"type": "complete", "total_ok": total_ok,
               "total": total * len(effective_slots)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _composite_to_b64(img: Image.Image, logo_path: Path, variant: str,
                      tmp: Path, index: int, slot: str) -> str:
    base_path = tmp / f"base_{index}_{slot}.png"
    final_path = tmp / f"final_{index}_{slot}.png"
    img.save(base_path, "PNG")
    composite(str(base_path), str(logo_path), str(final_path), variant,
              width_pct=LOGO_WIDTH_PCT, verbose=False)
    data = final_path.read_bytes()
    for p in (base_path, final_path):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    return base64.b64encode(data).decode("ascii")
