#!/usr/bin/env python3
"""
Multi-provider image generators
===============================
Each provider is a thin, single-attempt HTTP wrapper that returns a Pillow
``Image`` for one prompt, or raises a clean error. The retry / fallback /
minimum-size policy lives in ``orchestrator.py`` so that retry notices can be
streamed to the browser live, between attempts.

Contract every provider implements:

    class SomeGenerator(BaseGenerator):
        models: list[str]                       # primary first, fallbacks after
        supports_negative: bool
        supports_seed: bool
        def try_once(self, prompt, negative, model, seed) -> Image.Image
        def test_connection(self) -> tuple[bool, str]

Errors:
    GenerationError        -> retriable (rate limit, model cold, timeout, …)
    FatalGenerationError   -> do NOT retry (bad key, no access, bad request)
"""

from __future__ import annotations

import base64
import io
import random
from typing import List, Tuple

import requests
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Shared engine configuration (single source of truth)
# ---------------------------------------------------------------------------
IMG_SIZE = 1024          # square 1:1 output edge, in px
MIN_DIMENSION = 512      # reject + retry anything smaller (quality rule #2)
MAX_RETRIES = 3          # attempts per model before giving up (quality rule #3)
RETRY_BACKOFF = 5        # seconds, multiplied by attempt number
REQUEST_TIMEOUT = 180    # per HTTP request, seconds

BRAND_FOREST = (20, 42, 29)
BRAND_GOLD = (201, 168, 76)
BRAND_CREAM = (251, 247, 239)


class GenerationError(Exception):
    """A retriable failure — the orchestrator will back off and try again."""


class FatalGenerationError(GenerationError):
    """A non-retriable failure — bad key, no model access, malformed request."""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class BaseGenerator:
    name = "base"
    label = "Base"
    models: List[str] = []
    supports_negative = True
    supports_seed = True

    def __init__(self, api_key: str = "", dry_run: bool = False,
                 model: str | None = None):
        self.api_key = (api_key or "").strip()
        self.dry_run = dry_run
        if model:
            # A caller-chosen model is tried first, keeping the class fallbacks.
            self.models = [model] + [m for m in self.models if m != model]
        if not dry_run and not self.api_key:
            raise FatalGenerationError(
                f"{self.label}: an API key is required (or enable Dry Run).")
        self.session = requests.Session()

    # -- single attempt: override in subclasses -----------------------------
    def try_once(self, prompt: str, negative: str, model: str,
                 seed: int | None) -> Image.Image:
        raise NotImplementedError

    # -- connectivity check: override in subclasses -------------------------
    def test_connection(self) -> Tuple[bool, str]:
        raise NotImplementedError

    # -- dry-run stand-in ----------------------------------------------------
    def placeholder(self, prompt: str, label: str, brand_name: str,
                    slot: str) -> Image.Image:
        """A branded placeholder so the whole pipeline (compositing, gallery,
        zipping) can be exercised without spending API credits."""
        img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), BRAND_FOREST)
        d = ImageDraw.Draw(img)
        d.rectangle((28, 28, IMG_SIZE - 28, IMG_SIZE - 28),
                    outline=BRAND_GOLD, width=4)
        d.rectangle((28, 28, IMG_SIZE - 28, 210), fill=(14, 30, 21))
        d.text((60, 70), "DRY RUN — PLACEHOLDER", fill=BRAND_GOLD)
        d.text((60, 110), f"{brand_name}", fill=BRAND_CREAM)
        d.text((60, 150), f"{label}  ({slot})", fill=BRAND_CREAM)

        # Wrap the prompt so the layout/compositing can be judged visually.
        words, line, y = prompt.split(), "", 300
        for w in words[:90]:
            if len(line) + len(w) > 52:
                d.text((60, y), line, fill=(214, 222, 214))
                y += 26
                line = ""
            line += w + " "
        if line:
            d.text((60, y), line, fill=(214, 222, 214))
        d.text((60, IMG_SIZE - 70), f"via {self.label} (dry run)",
               fill=BRAND_GOLD)
        return img

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _bytes_to_image(data: bytes) -> Image.Image:
        try:
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:  # noqa: BLE001 - want the raw reason surfaced
            raise GenerationError(f"could not decode returned image: {e}")

    @staticmethod
    def _b64_to_image(b64: str) -> Image.Image:
        try:
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise GenerationError(f"could not decode base64 image: {e}")

    @staticmethod
    def _seed() -> int:
        return random.randint(1, 2_147_483_646)


# ---------------------------------------------------------------------------
# Provider 1 — HuggingFace Inference API
# ---------------------------------------------------------------------------
class HFGenerator(BaseGenerator):
    name = "huggingface"
    label = "HuggingFace"
    models = ["black-forest-labs/FLUX.1-dev",
              "stabilityai/stable-diffusion-xl-base-1.0"]
    supports_negative = True
    supports_seed = True
    API_ROOT = "https://api-inference.huggingface.co/models/"

    def try_once(self, prompt, negative, model, seed):
        params = {
            "guidance_scale": 7.0,
            "num_inference_steps": 30,
            "width": IMG_SIZE,
            "height": IMG_SIZE,
        }
        if negative:
            params["negative_prompt"] = negative
        if seed is not None:
            params["seed"] = seed
        payload = {"inputs": prompt, "parameters": params,
                   "options": {"wait_for_model": True}}
        try:
            r = self.session.post(
                self.API_ROOT + model,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Accept": "image/png"},
                json=payload, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise GenerationError("request timed out")
        except requests.RequestException as e:
            raise GenerationError(f"network error: {e}")

        if r.status_code == 200:
            ctype = r.headers.get("content-type", "")
            if "image" not in ctype:
                raise GenerationError(
                    f"non-image response ({ctype}): {r.text[:180]}")
            return self._bytes_to_image(r.content)
        if r.status_code == 503:
            raise GenerationError("model is loading (503)")
        if r.status_code == 429:
            raise GenerationError("rate limited (429)")
        if r.status_code == 401:
            raise FatalGenerationError("invalid HuggingFace token (401)")
        if r.status_code == 403:
            raise FatalGenerationError(
                "this token has no access to the model (403)")
        raise GenerationError(f"HTTP {r.status_code}: {r.text[:180]}")

    def test_connection(self):
        try:
            r = self.session.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20)
        except requests.RequestException as e:
            return False, f"network error: {e}"
        if r.status_code == 200:
            name = ""
            try:
                name = r.json().get("name", "")
            except ValueError:
                pass
            return True, f"Connected as {name}" if name else "Token valid"
        if r.status_code in (401, 403):
            return False, "Invalid HuggingFace token"
        return False, f"Unexpected response ({r.status_code})"


# ---------------------------------------------------------------------------
# Provider 2 — Google Gemini / Imagen  (priority provider — AI Studio quality)
# ---------------------------------------------------------------------------
class GeminiGenerator(BaseGenerator):
    name = "gemini"
    label = "Google Imagen"
    # imagen-4 is the AI-Studio-grade default; imagen-3 is the fallback.
    models = ["imagen-4.0-generate-001", "imagen-3.0-generate-002"]
    supports_negative = False   # Imagen 3+ dropped the negativePrompt field
    supports_seed = False       # seed needs watermark disabled; skip for safety
    ROOT = "https://generativelanguage.googleapis.com/v1beta"

    def try_once(self, prompt, negative, model, seed):
        url = f"{self.ROOT}/models/{model}:predict"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
        }
        try:
            r = self.session.post(
                url,
                headers={"x-goog-api-key": self.api_key,
                         "Content-Type": "application/json"},
                json=payload, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise GenerationError("request timed out")
        except requests.RequestException as e:
            raise GenerationError(f"network error: {e}")

        if r.status_code == 200:
            try:
                preds = r.json().get("predictions", [])
            except ValueError:
                raise GenerationError("malformed JSON from Imagen")
            if not preds:
                # Usually a safety block — surface it, do not hammer retries.
                raise FatalGenerationError(
                    "Imagen returned no image (prompt likely blocked by safety "
                    "filters)")
            b64 = preds[0].get("bytesBase64Encoded")
            if not b64:
                raise GenerationError("Imagen response missing image bytes")
            return self._b64_to_image(b64)

        msg = self._extract_error(r)
        if r.status_code in (400,):
            raise FatalGenerationError(f"Imagen rejected the request: {msg}")
        if r.status_code in (401, 403):
            raise FatalGenerationError(
                f"invalid Google API key or no Imagen access: {msg}")
        if r.status_code == 429:
            raise GenerationError("rate limited / quota exceeded (429)")
        raise GenerationError(f"HTTP {r.status_code}: {msg}")

    @staticmethod
    def _extract_error(r) -> str:
        try:
            return r.json().get("error", {}).get("message", r.text[:180])
        except ValueError:
            return r.text[:180]

    def test_connection(self):
        try:
            r = self.session.get(
                f"{self.ROOT}/models",
                headers={"x-goog-api-key": self.api_key}, timeout=20)
        except requests.RequestException as e:
            return False, f"network error: {e}"
        if r.status_code == 200:
            return True, "Google API key valid"
        if r.status_code in (400, 401, 403):
            return False, "Invalid Google API key"
        return False, f"Unexpected response ({r.status_code})"


# ---------------------------------------------------------------------------
# Provider 3 — Stability AI (Stable Image Core)
# ---------------------------------------------------------------------------
class StabilityGenerator(BaseGenerator):
    name = "stability"
    label = "Stability AI"
    models = ["core"]   # single endpoint; kept as a list for a uniform loop
    supports_negative = True
    supports_seed = True
    URL = "https://api.stability.ai/v2beta/stable-image/generate/core"

    def try_once(self, prompt, negative, model, seed):
        # Stability requires multipart/form-data. Sending each field as a
        # (None, value) tuple makes requests emit a proper multipart body.
        fields = {
            "prompt": (None, prompt),
            "aspect_ratio": (None, "1:1"),
            "output_format": (None, "png"),
        }
        if negative:
            fields["negative_prompt"] = (None, negative)
        if seed is not None:
            fields["seed"] = (None, str(seed))
        try:
            r = self.session.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Accept": "image/*"},
                files=fields, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise GenerationError("request timed out")
        except requests.RequestException as e:
            raise GenerationError(f"network error: {e}")

        if r.status_code == 200:
            return self._bytes_to_image(r.content)
        msg = self._extract_error(r)
        if r.status_code == 401:
            raise FatalGenerationError("invalid Stability API key (401)")
        if r.status_code == 403:
            raise FatalGenerationError(
                f"Stability blocked the request (403): {msg}")
        if r.status_code == 429:
            raise GenerationError("rate limited (429)")
        if r.status_code == 402:
            raise FatalGenerationError("Stability account out of credits (402)")
        raise GenerationError(f"HTTP {r.status_code}: {msg}")

    @staticmethod
    def _extract_error(r) -> str:
        try:
            j = r.json()
            errs = j.get("errors")
            if errs:
                return "; ".join(errs)
            return j.get("message", r.text[:180])
        except ValueError:
            return r.text[:180]

    def test_connection(self):
        try:
            r = self.session.get(
                "https://api.stability.ai/v1/user/account",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20)
        except requests.RequestException as e:
            return False, f"network error: {e}"
        if r.status_code == 200:
            return True, "Stability API key valid"
        if r.status_code in (401, 403):
            return False, "Invalid Stability API key"
        return False, f"Unexpected response ({r.status_code})"


# ---------------------------------------------------------------------------
# Provider 4 — Together AI (FLUX.1-schnell free tier)
# ---------------------------------------------------------------------------
class TogetherGenerator(BaseGenerator):
    name = "together"
    label = "Together AI"
    models = ["black-forest-labs/FLUX.1-schnell-Free"]
    # FLUX-schnell does not use negatives; skip to avoid 422s on the free tier.
    supports_negative = False
    supports_seed = True
    URL = "https://api.together.xyz/v1/images/generations"

    def try_once(self, prompt, negative, model, seed):
        payload = {
            "model": model,
            "prompt": prompt,
            "width": IMG_SIZE,
            "height": IMG_SIZE,
            "steps": 4,           # schnell is a 1–4 step model
            "n": 1,
            "response_format": "b64_json",
        }
        if seed is not None:
            payload["seed"] = seed
        try:
            r = self.session.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json=payload, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise GenerationError("request timed out")
        except requests.RequestException as e:
            raise GenerationError(f"network error: {e}")

        if r.status_code == 200:
            try:
                data = r.json().get("data", [])
            except ValueError:
                raise GenerationError("malformed JSON from Together")
            if not data:
                raise GenerationError("Together returned no image")
            item = data[0]
            if item.get("b64_json"):
                return self._b64_to_image(item["b64_json"])
            if item.get("url"):
                img = self._download(item["url"])
                return img
            raise GenerationError("Together response missing image data")
        msg = self._extract_error(r)
        if r.status_code == 401:
            raise FatalGenerationError("invalid Together API key (401)")
        if r.status_code == 403:
            raise FatalGenerationError(f"Together access denied (403): {msg}")
        if r.status_code == 429:
            raise GenerationError("rate limited (429)")
        raise GenerationError(f"HTTP {r.status_code}: {msg}")

    def _download(self, url: str) -> Image.Image:
        try:
            r = self.session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise GenerationError(f"could not fetch image url: {e}")
        if r.status_code != 200:
            raise GenerationError(f"image url returned {r.status_code}")
        return self._bytes_to_image(r.content)

    @staticmethod
    def _extract_error(r) -> str:
        try:
            j = r.json()
            err = j.get("error")
            if isinstance(err, dict):
                return err.get("message", r.text[:180])
            if isinstance(err, str):
                return err
            return r.text[:180]
        except ValueError:
            return r.text[:180]

    def test_connection(self):
        try:
            r = self.session.get(
                "https://api.together.xyz/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20)
        except requests.RequestException as e:
            return False, f"network error: {e}"
        if r.status_code == 200:
            return True, "Together API key valid"
        if r.status_code in (401, 403):
            return False, "Invalid Together API key"
        return False, f"Unexpected response ({r.status_code})"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_REGISTRY = {
    HFGenerator.name: HFGenerator,
    GeminiGenerator.name: GeminiGenerator,
    StabilityGenerator.name: StabilityGenerator,
    TogetherGenerator.name: TogetherGenerator,
}


def provider_catalog() -> list[dict]:
    """Public, secret-free description of every provider for the UI."""
    meta = {
        "huggingface": {
            "quality": "High — FLUX.1-dev, SDXL fallback",
            "key_help": "Create a READ token at huggingface.co/settings/tokens",
            "free_tier": True,
        },
        "gemini": {
            "quality": "Highest — Imagen 4 (matches Google AI Studio)",
            "key_help": "Get a key at aistudio.google.com/app/apikey",
            "free_tier": True,
        },
        "stability": {
            "quality": "High — Stable Image Core",
            "key_help": "Get a key at platform.stability.ai/account/keys",
            "free_tier": False,
        },
        "together": {
            "quality": "Fast & free — FLUX.1-schnell",
            "key_help": "Get a key at api.together.xyz/settings/api-keys",
            "free_tier": True,
        },
    }
    out = []
    for name, cls in _REGISTRY.items():
        m = meta[name]
        out.append({
            "id": name,
            "label": cls.label,
            "models": cls.models,
            "supports_negative": cls.supports_negative,
            "quality": m["quality"],
            "key_help": m["key_help"],
            "free_tier": m["free_tier"],
        })
    return out


def make_generator(provider: str, api_key: str = "", dry_run: bool = False,
                   model: str | None = None) -> BaseGenerator:
    cls = _REGISTRY.get((provider or "").lower())
    if cls is None:
        raise FatalGenerationError(
            f"Unknown provider '{provider}'. Choose one of "
            f"{', '.join(_REGISTRY)}.")
    return cls(api_key=api_key, dry_run=dry_run, model=model)
