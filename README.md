# Brand-Locked Image Generator

Upload a logo, **lock it in**, and batch-generate on-brand product imagery from
a prompt. Four studio-grade 1:1 images per product — a Hero shot plus three
posters — with your exact logo composited **programmatically** (never described
to the model, so it is pixel-identical on every asset). Swap providers and API
keys from the UI; keys live only in your browser.

Built on the proven Gau Bhoomi Naturals pipeline (`gbn_prompts.py`,
`gbn_composite.py`, `gbn_pipeline.py`), wrapped in a FastAPI service and a
polished single-page web app.

<br>

## Why one server

The whole app is **one FastAPI process** that serves both the JSON/SSE API and
the static frontend. That means:

- **One command to run**, one Dockerfile to deploy, no CORS, no `BACKEND_URL`.
- Server-Sent Events stream same-origin, so images appear the instant each one
  finishes.
- Zero configuration: no environment variables, no database. API keys arrive
  per request from the browser and are discarded when the request ends;
  uploaded logos are written to a unique temp file only for the duration of a
  run, then deleted.

<br>

## Quick start (local)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**, then:

1. **Dry Run** (top-right) — flip it on to test the whole pipeline with no API
   key and no credits spent. Great first run.
2. **Brand Logo** — drop a transparent **PNG**, set the brand name, it locks.
3. **What to generate** — pick a mode (below) and describe your product.
4. **Generate** — images stream into the gallery; download singles, a per-
   product ZIP, or the whole batch as a ZIP.

For a real run, open **API Keys**, paste a key for one provider, hit **Test**
(green dot = good), select it, and turn Dry Run off.

<br>

## The four images per product

| Slot | File | Logo |
|---|---|---|
| Hero shot | `01_Hero.png` | none — the product label carries the brand |
| Process poster | `02_Process.png` | 22% width, top-center, cream backing strip |
| Lifestyle poster | `03_Lifestyle.png` | 22% width, top-center, cream backing strip |
| Flat lay | `04_FlatLay.png` | 22% width, top-center, transparent backing |

<br>

## Three ways to prompt — works for any product, any brand

- **Auto Prompts** — enter product name, size, category. Click **Preview** to
  see and edit all four before generating.
- **Custom Prompts** — write all four yourself; brand quality tokens and a
  "keep the top clear for the logo" rule are appended automatically.
- **Batch CSV** — upload `product_name,size,category`; every row runs its own
  uniqueness-checked prompt set with a live progress bar.

Auto and Batch never hard-fail on an unrecognised product. There are 11
hand-tuned profiles (ghee, coconut, mustard, groundnut, sesame, sunflower,
castor, walnut, almond) that get fully bespoke prompts. **Anything else** —
electronics, apparel, beauty, packaged food, or literally anything —
automatically falls through to a universal fallback engine
(`generate_any_product_prompts` in `backend/gbn_prompts.py`) that classifies
the product into one of six template families from its category/name and
generates a coherent, on-brand, deterministic 4-slot prompt set on the fly. A
small badge ("smart generic template") shows when this path was used, purely
informational — nothing ever blocks or errors out. To add a fully bespoke
profile instead, append to `PROFILES` in `backend/gbn_prompts.py` and run
`python backend/gbn_prompts.py` to confirm the uniqueness audit still passes.

<br>

## Providers

| Provider | Model(s) | Notes |
|---|---|---|
| **Google Imagen** | `imagen-4.0-generate-001` → `imagen-3.0` | Highest quality — matches Google AI Studio |
| **HuggingFace** | `FLUX.1-dev` → `SDXL` | Free tier; automatic fallback |
| **Stability AI** | Stable Image Core | Paid credits |
| **Together AI** | `FLUX.1-schnell-Free` | Fast and free |

Each attempt is retried up to 3× with backoff; if the primary model keeps
failing the pipeline falls back to the secondary model, all streamed live to
the log panel. Images under 512×512 are rejected and retried (quality rule).
Keys are validated with a lightweight probe by the **Test** button.

<br>

## Get an API key

- **Google Imagen** — https://aistudio.google.com/app/apikey
- **HuggingFace** — https://huggingface.co/settings/tokens (READ scope is enough)
- **Stability AI** — https://platform.stability.ai/account/keys
- **Together AI** — https://api.together.xyz/settings/api-keys

<br>

## Deploy

### Docker (any host)

```bash
docker build -t brand-image-gen .
docker run -p 8000:8000 brand-image-gen
```

### Railway / Render / Fly

Point the platform at this repo. The `Dockerfile` builds everything and honors
the injected `$PORT`. No environment variables are required. That's the whole
setup.

<br>

## API reference

All SSE endpoints stream newline-delimited `data: {json}` events.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | liveness + profile count |
| `GET` | `/api/providers` | provider catalog for the UI |
| `POST` | `/api/audit` | run `audit_uniqueness()` → `{passed, issues}` |
| `POST` | `/api/preview-prompts` | 4 auto prompts (or available profiles on miss) |
| `POST` | `/api/test-connection` | validate a provider key |
| `POST` | `/api/generate` | **SSE** — one product (auto / custom / raw / retry) |
| `POST` | `/api/generate-batch` | **SSE** — many products from a list |

SSE event types: `audit`, `batch_start`, `product_start`, `prompts`,
`progress`, `image`, `error`, `product_complete`, `complete`, `fatal`.

<br>

## Command-line pipeline (optional)

The original CLI still works for scripted/batch runs:

```bash
cd backend
export HF_TOKEN=hf_xxx
python gbn_pipeline.py --product "A2 Gir Cow Ghee Bilona" \
    --size "500ml" --category "Ghee" --logo logo.png
python gbn_pipeline.py --batch products.csv --logo logo.png --dry-run
```

<br>

## Tests

No network or keys required — the suite runs the full pipeline in dry-run:

```bash
python tests/test_pipeline.py
```

It covers prompt generation, the uniqueness audit, brand-name threading, logo
compositing (hero has no logo; posters do), batch, custom/raw prompts, single-
slot retry, and the unmatched-profile and missing-logo error paths. CI runs it
on every push (`.github/workflows/ci.yml`).

<br>

## Project layout

```
brand-locked-image-gen/
├── backend/
│   ├── main.py            FastAPI app: endpoints + serves the frontend
│   ├── generators.py      BaseGenerator + HF / Imagen / Stability / Together
│   ├── orchestrator.py    SSE event stream, retry/fallback, logo compositing
│   ├── gbn_prompts.py     prompt engine (+ optional brand_name)
│   ├── gbn_composite.py   Pillow logo compositor (unchanged)
│   ├── gbn_pipeline.py    original CLI (unchanged behavior)
│   ├── products.csv       sample batch
│   └── requirements.txt
├── frontend/
│   ├── index.html · styles.css · app.js
│   └── zip.js             dependency-free ZIP writer (client-side downloads)
├── tests/test_pipeline.py
├── Dockerfile
└── .github/workflows/ci.yml
```

<br>

## Guarantees preserved from the original pipeline

1. The logo is never described to the model — always composited by Pillow.
2. Minimum image size 512×512; smaller is rejected and retried.
3. Up to 3 retries per image before it is reported as failed.
4. Comprehensive negative prompts on every generation.
5. Hero gets no logo; the three posters get the logo at 22% width, top-center.
6. `audit_uniqueness()` runs before every batch.
7. Every product gets unique props, scenes, and taglines — never reused.
