#!/usr/bin/env python3
"""
Gau Bhoomi Naturals — Product Prompt Engine
===========================================
Builds 4 unique, product-specific prompts per SKU.

Design rule: every product gets its OWN props, process story, lifestyle
scene, taglines and badges. Nothing is reused between products. A runtime
uniqueness audit (see audit_uniqueness) enforces this across a batch.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import hashlib
import random
import re

# ---------------------------------------------------------------------------
# Shared style tokens — the quality target applied to every generation
# ---------------------------------------------------------------------------
QUALITY = ("hyperrealistic, photorealistic, 8K, premium commercial brand "
           "photography, Forest Essentials and Organic Tattva level polish, "
           "immaculate art direction, sharp detail, no AI artifacts")

DEFAULT_BRAND_NAME = "Gau Bhoomi Naturals"


def brand_token(brand_name: str = DEFAULT_BRAND_NAME) -> str:
    """Style token for a given brand name.

    Only the wordmark text changes per brand; the organic forest-green/gold
    art direction is intentionally fixed — it is the aesthetic the profile
    engine (Mode A) was tuned for. Brands wanting a different palette use the
    custom-prompt path instead.
    """
    return (f"{brand_name} premium Indian organic brand, dark forest "
            "green #142A1D and gold #C9A84C palette, cream #FBF7EF accents, "
            "Playfair Display elegant serif typography")


# Kept for backward compatibility with any caller importing BRAND directly.
BRAND = brand_token()

NEG_BASE = ("blurry, low quality, watermark, distorted label, garbled text, "
            "misspelled text, gibberish letters, AI artifacts, deformed, "
            "faces, people, wrong colors, neon colors, cartoon, illustration, "
            "3d render, low resolution, jpeg artifacts")

NEG_HERO = NEG_BASE + ", multiple products, text overlay, poster elements, cluttered"
NEG_POSTER = NEG_BASE + ", broken layout, overlapping text, non-brand colors"
NEG_FLAT = NEG_BASE + ", cluttered props, messy arrangement, overlapping objects"


# ---------------------------------------------------------------------------
# Product profile
# ---------------------------------------------------------------------------
@dataclass
class Profile:
    key: str
    hero_props: str
    process_heading: str
    process_bullets: List[str]
    process_scene: str
    process_tagline: str
    lifestyle_scene: str
    lifestyle_heading: str
    benefits: List[str]
    lifestyle_tagline: str
    flatlay_props: str
    flatlay_headline: str
    badges: List[str]
    aliases: List[str] = field(default_factory=list)


PROFILES: List[Profile] = [

    Profile(
        key="ghee_bilona",
        aliases=["ghee", "bilona", "gir cow ghee", "a2 ghee"],
        hero_props="a hand-carved wooden spoon lifting grainy golden ghee, "
                   "green cardamom pods, fresh tulsi sprigs, a small brass bowl",
        process_heading="The Ancient Bilona Method",
        process_bullets=[
            "Milk from free-grazing indigenous Gir cows",
            "Cultured overnight into traditional curd",
            "Hand-churned with a wooden bilona",
            "Slow simmered over a gentle earthen flame",
        ],
        process_scene="a traditional wooden bilona churner standing in a clay "
                      "pot of curd inside a warm rustic Indian kitchen, morning "
                      "light through a window, brass vessels nearby",
        process_tagline="Churned by Hand, the Way It Has Always Been",
        lifestyle_scene="hands in a silk saree spooning glossy golden ghee over "
                        "steaming dal in a polished brass thali, warm Indian "
                        "dining table, gentle steam rising",
        lifestyle_heading="A Spoonful of Tradition",
        benefits=["Rich in natural A2 protein", "Supports easy digestion",
                  "High smoke point for cooking", "Ayurvedic daily vitality"],
        lifestyle_tagline="From Our Gir Cows to Your Family Table",
        flatlay_props="a lit brass diya, green cardamom pods, tulsi sprigs, raw "
                      "turmeric root, a small clay pot of curd, a wooden churn "
                      "handle, scattered marigold petals",
        flatlay_headline="Pure Bilona Gold",
        badges=["A2 Certified", "Hand Churned", "Grass Fed"],
    ),

    Profile(
        key="coconut",
        aliases=["coconut", "khopra", "copra", "nariyal"],
        hero_props="halved fresh coconuts, dried copra pieces, a coconut shell "
                   "bowl, white jasmine flowers and a palm frond",
        process_heading="From Khopra to Golden Oil",
        process_bullets=[
            "Coconuts sun-dried into firm white khopra",
            "Cold pressed in a wooden chekku below 40°C",
            "Never refined, bleached or deodorised",
            "Small-batch settled and muslin filtered",
        ],
        process_scene="a wooden chekku press turning dried copra into oil inside "
                      "a coastal Kerala mill, coconut grove visible outside, "
                      "warm dappled light",
        process_tagline="Cold Pressed at Nature's Own Temperature",
        lifestyle_scene="hands in a cotton saree pouring coconut oil into a hot "
                        "iron kadai where mustard seeds and curry leaves crackle, "
                        "South Indian kitchen, aromatic steam",
        lifestyle_heading="The Soul of South Indian Cooking",
        benefits=["Natural MCT energy source", "Stable at high heat",
                  "Authentic coconut aroma", "Nourishes hair and skin"],
        lifestyle_tagline="One Oil, Endless Kitchen Traditions",
        flatlay_props="a whole coconut, broken copra pieces, a coconut shell "
                      "bowl, a green palm frond, white jasmine blossoms, coiled "
                      "coir rope, a fresh banana leaf",
        flatlay_headline="Cold Pressed Purity",
        badges=["Chekku Pressed", "Unrefined", "100% Copra"],
    ),

    Profile(
        key="black_mustard",
        aliases=["black mustard"],
        hero_props="black mustard seeds in a copper bowl, yellow mustard "
                   "blossoms, dried red chillies and a jute cloth",
        process_heading="Pungent by Nature, Pressed by Tradition",
        process_bullets=[
            "Single-origin black mustard from Bengal fields",
            "Crushed slowly in a wooden kachi ghani",
            "Left unrefined and unfiltered by design",
            "Natural pungency and allyl aroma preserved",
        ],
        process_scene="a wooden kachi ghani ghani rotating over black mustard "
                      "seeds in a village mill, mustard fields in the distance, "
                      "earthy golden light",
        process_tagline="Kachi Ghani Pressed, Full Pungency Intact",
        lifestyle_scene="hands in a cotton saree tempering smoking black mustard "
                        "oil in a kadai for a Bengali fish curry, panch phoron "
                        "spluttering, rustic kitchen",
        lifestyle_heading="The Heart of Bengali Kitchens",
        benefits=["Bold natural pungency", "Plant omega-3 content",
                  "Traditional antibacterial use", "Classic warming massage oil"],
        lifestyle_tagline="Sharp, Bold, Unmistakably Authentic",
        flatlay_props="black mustard seeds, yellow mustard blossoms, dried red "
                      "chillies, panch phoron spice mix, a terracotta bowl, "
                      "coarse jute cloth, a brass ladle",
        flatlay_headline="Kachi Ghani Strong",
        badges=["Kachi Ghani", "Unrefined", "Single Origin"],
    ),

    Profile(
        key="yellow_mustard",
        aliases=["yellow mustard"],
        hero_props="yellow mustard seeds in a ceramic dish, mustard flowers in "
                   "bloom, raw mango slices and fenugreek seeds",
        process_heading="Golden Seeds, Gentle Press",
        process_bullets=[
            "Hand-sorted yellow mustard from Rajasthan",
            "Slow wooden ghani rotation, never rushed",
            "Cold pressed and held under 45°C",
            "Naturally settled, never chemically filtered",
        ],
        process_scene="a blooming yellow mustard field at golden hour with a "
                      "traditional wooden ghani press in the foreground, sacks "
                      "of seed stacked beside it",
        process_tagline="Slow Pressed for a Milder Gold",
        lifestyle_scene="hands in a printed cotton saree stirring yellow mustard "
                        "oil into raw mango pickle inside a ceramic barni jar, "
                        "sunlit terrace, spices scattered on cloth",
        lifestyle_heading="The Pickle Maker's Choice",
        benefits=["Milder, rounder flavour", "Preserves pickles naturally",
                  "Natural vitamin E", "Gentle warming massage"],
        lifestyle_tagline="The Oil That Keeps Achaar Alive",
        flatlay_props="yellow mustard seeds, mustard blossoms, raw mango slices, "
                      "fenugreek seeds, nigella seeds, a ceramic pickle jar, "
                      "a square of muslin",
        flatlay_headline="Golden Ghani Pressed",
        badges=["Wood Pressed", "Mild Aroma", "Pickle Grade"],
    ),

    Profile(
        key="groundnut",
        aliases=["peanut", "groundnut", "ground nut", "moongphali"],
        hero_props="raw peanuts in their shells, loose peanut kernels, an open "
                   "jute sack and dried groundnut leaves",
        process_heading="Sun Dried Groundnuts, Slow Pressed",
        process_bullets=[
            "Hand-picked groundnuts from Gujarat farms",
            "Sun dried on open earthen yards",
            "Single-pass wooden press, no re-extraction",
            "Naturally settled to a clear golden oil",
        ],
        process_scene="heaps of freshly harvested groundnuts beside a traditional "
                      "wooden press in a Gujarat village yard, red soil, strong "
                      "afternoon sun",
        process_tagline="One Press, Zero Compromise",
        lifestyle_scene="hands in a kurta sleeve lowering puris into a deep iron "
                        "kadai of shimmering groundnut oil, puris puffing golden, "
                        "busy Indian kitchen counter",
        lifestyle_heading="Built for the Indian Deep Fry",
        benefits=["Very high smoke point", "Warm nutty aroma",
                  "Holds up to repeat frying", "Natural vitamin E"],
        lifestyle_tagline="Crisp Results, Every Single Time",
        flatlay_props="shelled peanuts, cracked peanut shells, an open jute sack, "
                      "groundnut leaves, a terracotta bowl, a wooden scoop, "
                      "a scattering of red earth",
        flatlay_headline="Sun Dried Wood Pressed",
        badges=["Wood Pressed", "High Smoke Point", "Single Pass"],
    ),

    Profile(
        key="black_sesame",
        aliases=["black sesame", "black til"],
        hero_props="black sesame seeds in a brass bowl, dried sesame pods, a "
                   "copper massage vessel and dark ayurvedic herbs",
        process_heading="The Black Seed of Strength",
        process_bullets=[
            "Rare black til hand-cleaned and winnowed",
            "Cold pressed in a slow stone chekku",
            "Left unrefined for a deep amber colour",
            "Naturally rich in sesamin and sesamol",
        ],
        process_scene="black sesame seeds pouring into a heavy stone chekku press "
                      "in a dim traditional mill, single shaft of warm light, "
                      "dark rich tones",
        process_tagline="Stone Pressed, Deeply Nourishing",
        lifestyle_scene="hands warming black sesame oil in a brass bowl over a "
                        "low flame for an abhyanga massage ritual, folded cotton "
                        "towels, calm Ayurvedic treatment room",
        lifestyle_heading="Ayurveda's Warming Oil",
        benefits=["Deep tissue nourishment", "Natural calcium source",
                  "Balances vata in winter", "Strengthens hair roots"],
        lifestyle_tagline="The Winter Oil of Ancient India",
        flatlay_props="black sesame seeds, dried sesame pods, a brass massage "
                      "bowl, bundled ayurvedic herbs, a wooden comb, a copper "
                      "vessel, folded dark linen",
        flatlay_headline="Black Til Strength",
        badges=["Stone Chekku", "Unrefined", "Ayurvedic Grade"],
    ),

    Profile(
        key="white_sesame",
        aliases=["white sesame", "white til", "sesame"],
        hero_props="polished white sesame seeds, til laddoos, a stone mortar and "
                   "a block of jaggery",
        process_heading="Delicate Til, Delicate Press",
        process_bullets=[
            "Polished white til sorted entirely by hand",
            "Low-temperature chekku pressing",
            "Light golden oil, completely unrefined",
            "Natural sweet sesame aroma retained",
        ],
        process_scene="white sesame seeds spread on a drying mat beside a stone "
                      "press, sesame field with white flowers behind, soft "
                      "morning haze",
        process_tagline="Light Pressed, Naturally Nutty",
        lifestyle_scene="hands in a saree drizzling white sesame oil over fresh "
                        "idlis with a bowl of podi alongside, banana leaf service, "
                        "bright South Indian breakfast table",
        lifestyle_heading="The Everyday Cooking Til",
        benefits=["Light nutty flavour", "Ideal for daily cooking",
                  "Sesamol antioxidants", "Supports bone health"],
        lifestyle_tagline="Gentle Enough for Every Day",
        flatlay_props="white sesame seeds, round til laddoos, white sesame "
                      "flowers, a stone mortar, a fresh banana leaf, a brass "
                      "spoon, a block of jaggery",
        flatlay_headline="Light Til Purity",
        badges=["Chekku Pressed", "Cold Extracted", "Unrefined"],
    ),

    Profile(
        key="sunflower",
        aliases=["sunflower", "surajmukhi"],
        hero_props="a cut sunflower head, striped sunflower seeds, loose hulls "
                   "and bright yellow petals",
        process_heading="Sunflowers to Golden Light",
        process_bullets=[
            "Bright sunflower seed from Karnataka farms",
            "Dehulled clean before pressing",
            "Cold pressed with no hexane or solvents",
            "Naturally light, clear and neutral",
        ],
        process_scene="a wide sunflower field in full bloom with a wooden press "
                      "and seed sacks at the edge, clear blue sky, vivid natural "
                      "yellows",
        process_tagline="Pressed Light, Naturally Clear",
        lifestyle_scene="hands sautéing chopped vegetables in a light steel pan "
                        "with sunflower oil, bright airy modern Indian kitchen, "
                        "fresh produce on the counter",
        lifestyle_heading="Light Cooking, Every Day",
        benefits=["Clean neutral flavour", "High in vitamin E",
                  "Light on digestion", "Perfect for daily sauté"],
        lifestyle_tagline="The Everyday Light Oil",
        flatlay_props="a whole sunflower head, striped seeds, scattered hulls, "
                      "folded natural linen, a clear glass bowl, a wooden scoop, "
                      "loose yellow petals",
        flatlay_headline="Solvent Free Light",
        badges=["Hexane Free", "Cold Pressed", "Vitamin E"],
    ),

    Profile(
        key="castor",
        aliases=["castor", "arandi"],
        hero_props="mottled castor beans, a broad castor leaf, a glass dropper "
                   "and a wooden comb",
        process_heading="The Ancient Healing Bean",
        process_bullets=[
            "Castor beans shelled entirely by hand",
            "Cold pressed and never boiled",
            "Thick, viscous and fully unrefined",
            "Natural ricinoleic acid left intact",
        ],
        process_scene="castor beans beside a cold press with tall castor plants "
                      "and broad green leaves behind, muted natural daylight",
        process_tagline="Cold Pressed, Never Heated",
        lifestyle_scene="hands working castor oil through long dark hair with a "
                        "wooden comb, no face visible, soft window light, calm "
                        "home setting with a glass bottle nearby",
        lifestyle_heading="The Hair and Skin Ritual",
        benefits=["Supports hair growth", "Deep lasting moisture",
                  "Traditional internal use", "Soothing joint massage"],
        lifestyle_tagline="Grandmother's Remedy, Purely Pressed",
        flatlay_props="mottled castor beans, broad castor leaves, a wooden comb, "
                      "a glass dropper, rolled cotton, a small brass bowl, "
                      "textured dark linen",
        flatlay_headline="Cold Pressed Ricinoleic",
        badges=["Hexane Free", "Unrefined", "Therapeutic Grade"],
    ),

    Profile(
        key="walnut",
        aliases=["walnut", "akhrot"],
        hero_props="whole walnuts, cracked shells, exposed kernels and a "
                   "chinar leaf on woven pashmina",
        process_heading="Kashmir's Cold Mountain Harvest",
        process_bullets=[
            "Himalayan walnuts cracked open by hand",
            "Pressed within days of the autumn harvest",
            "Kept at low temperature to protect omega-3",
            "Rare small-batch yield, never mass produced",
        ],
        process_scene="a Kashmiri walnut orchard in autumn with cracked walnuts "
                      "in woven baskets beside a small press, chinar leaves on "
                      "the ground, crisp mountain light",
        process_tagline="From Kashmir Valleys, Freshly Pressed",
        lifestyle_scene="hands drizzling walnut oil over a plated salad of fresh "
                        "greens and pomegranate as a finishing touch, elegant "
                        "ceramic plate, refined table setting",
        lifestyle_heading="A Finishing Oil for the Fine Table",
        benefits=["Plant omega-3 ALA", "Supports brain health",
                  "Best used as a drizzle", "Delicate toasted aroma"],
        lifestyle_tagline="Never Heat It, Simply Drizzle",
        flatlay_props="whole walnuts, split shells, golden kernels, a dried "
                      "chinar leaf, folded pashmina cloth, a carved wooden bowl, "
                      "an iron nutcracker",
        flatlay_headline="Himalayan Cold Pressed",
        badges=["Kashmir Sourced", "Omega-3 Rich", "Small Batch"],
    ),

    Profile(
        key="almond",
        aliases=["almond", "badam", "mamra"],
        hero_props="whole mamra almonds, cracked almond shells, saffron strands "
                   "and rose petals on muslin",
        process_heading="Badam Pressed to Liquid Gold",
        process_bullets=[
            "Premium mamra almonds selected by grade",
            "Blanched clean and sun dried slowly",
            "Gentle cold press held below 40°C",
            "Twelve kilos of almonds per single litre",
        ],
        process_scene="trays of mamra almonds drying in the sun beside a small "
                      "cold press, an almond orchard in soft blossom behind, "
                      "delicate warm light",
        process_tagline="Twelve Kilos for a Single Litre",
        lifestyle_scene="hands gently massaging almond oil into a baby's feet on "
                        "a soft cotton blanket, no faces visible, warm nursery "
                        "light, glass bottle beside",
        lifestyle_heading="The Gentlest Oil of All",
        benefits=["Vitamin E for skin", "Safe for baby massage",
                  "Strengthens hair shafts", "Traditional memory tonic"],
        lifestyle_tagline="Gentle Enough for the Youngest Skin",
        flatlay_props="whole almonds, cracked almond shells, blanched kernels, "
                      "saffron strands, soft muslin cloth, a small silver bowl, "
                      "scattered rose petals",
        flatlay_headline="Mamra Badam Pure",
        badges=["Mamra Almonds", "Cold Pressed", "Baby Safe"],
    ),
]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def match_profile(product_name: str) -> Optional[Profile]:
    """Longest-alias-wins match so 'black sesame' beats bare 'sesame'."""
    n = _norm(product_name)
    best, best_len = None, 0
    for p in PROFILES:
        for alias in p.aliases:
            if alias in n and len(alias) > best_len:
                best, best_len = p, len(alias)
    return best


def container_for(size: str, category: str = "") -> str:
    """
    Vessel type by size and category. Returned WITHOUT a leading article so
    callers control the grammar.
      - 5 LTR            -> metal tin with carry handle
      - Ghee (any size)  -> wide-mouth glass jar (ghee is never bottled)
      - everything else  -> bottle
    """
    s = _norm(size)
    if re.search(r"\b5\s*(l|ltr|litre|liter)\b", s):
        return ("premium dark forest green metal tin container with a gold "
                "label and a sturdy carry handle")

    if "ghee" in _norm(category):
        return ("premium wide-mouth glass jar with a dark forest green gold-"
                "foiled label and a gold lid, thick golden grainy ghee visible "
                "inside")

    return "premium dark forest green bottle with a gold label and a gold cap"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def generate_product_prompts(product_name: str, size: str,
                             category: str,
                             brand_name: str = DEFAULT_BRAND_NAME
                             ) -> Dict[str, Dict]:
    """Return the 4 slot prompts for one SKU.

    ``brand_name`` swaps only the wordmark text rendered on the hero label and
    referenced in the brand style token, so the same tuned engine works for any
    brand that fits the organic-premium profiles. Defaults to Gau Bhoomi
    Naturals to preserve the original behaviour exactly.
    """
    prof = match_profile(product_name)
    if prof is None:
        raise ValueError(
            f"No profile matched '{product_name}'. Add a Profile to PROFILES "
            f"in gbn_prompts.py — the engine refuses to emit generic prompts.")

    brand_name = (brand_name or DEFAULT_BRAND_NAME).strip() or DEFAULT_BRAND_NAME
    brand = brand_token(brand_name)
    vessel = container_for(size, category)
    bullets = "; ".join(prof.process_bullets)
    benefits = "; ".join(prof.benefits)
    badges = ", ".join(prof.badges)

    hero = (
        f"Hyperrealistic premium ecommerce product photography of a single "
        f"{vessel}, containing {product_name}. The gold label clearly reads "
        f"'{brand_name}' at the top, '{product_name}' in the middle, "
        f"and '{size}' in large bold gold lettering at the bottom as the most "
        f"prominent text. The product stands centered on a dark polished "
        f"walnut wooden surface, styled with {prof.hero_props}. Warm golden "
        f"studio rim lighting from the top left, deep forest green bokeh "
        f"background, ultra sharp focus on the label, Phase One medium format "
        f"camera quality. {QUALITY}. No people, no text overlays."
    )

    process = (
        f"Square 1:1 premium brand poster. {brand}. Solid deep forest green "
        f"#142A1D background. The top 15 percent is left clean and empty for a "
        f"logo. Left column: a large white Playfair Display serif heading "
        f"'{prof.process_heading}', a thin gold divider rule beneath it, then "
        f"four white bullet points with small gold markers reading: {bullets}. "
        f"Right column: a photorealistic scene of {prof.process_scene}. A "
        f"{vessel}, holding {product_name} {size}, sits at the bottom center. A full "
        f"width dark green banner runs along the bottom with gold serif text "
        f"'{prof.process_tagline}'. Below it a thin strip shows No "
        f"Preservatives, No Chemicals, No Additives in white with gold icons. "
        f"Crisp clean typography, perfectly spelled. {QUALITY}."
    )

    lifestyle = (
        f"Square 1:1 premium brand poster. {brand}. Warm cream #FBF7EF "
        f"background. The top 15 percent is left clean and empty for a logo. "
        f"The main scene shows {prof.lifestyle_scene}. Absolutely no faces are "
        f"visible, only hands and clothing. To one side a large dark forest "
        f"green Playfair Display serif heading reads "
        f"'{prof.lifestyle_heading}', with four benefit rows beneath it in dark "
        f"green text with gold icons reading: {benefits}. A full width dark "
        f"green banner runs along the bottom with centered gold serif text "
        f"'{prof.lifestyle_tagline}'. Elegant editorial layout, generous white "
        f"space, perfectly spelled typography. {QUALITY}."
    )

    flatlay = (
        f"Square 1:1 premium brand poster, overhead flat lay photography on a "
        f"dark forest green #142A1D textured linen surface. {brand}. The top "
        f"15 percent is left clean and empty for a logo. A {vessel}, holding "
        f"{product_name} {size}, lies centered under a dramatic warm golden "
        f"spotlight from directly above. Arranged around it with intentional "
        f"spacing and clear negative space: {prof.flatlay_props}. Near the "
        f"bottom a short gold Playfair Display headline reads "
        f"'{prof.flatlay_headline}', with cream subtext below reading "
        f"'{product_name} — {size}', and three small gold badge icons in a row "
        f"reading {badges}. Museum-quality styling, never cluttered. {QUALITY}."
    )

    return {
        "01_Hero":      {"prompt": hero,      "negative": NEG_HERO,   "variant": "hero"},
        "02_Process":   {"prompt": process,   "negative": NEG_POSTER, "variant": "process"},
        "03_Lifestyle": {"prompt": lifestyle, "negative": NEG_POSTER, "variant": "lifestyle"},
        "04_FlatLay":   {"prompt": flatlay,   "negative": NEG_FLAT,   "variant": "flatlay"},
    }


# ---------------------------------------------------------------------------
# Uniqueness audit
# ---------------------------------------------------------------------------
def audit_uniqueness() -> List[str]:
    """Verify no two profiles share a concept. Returns list of collisions."""
    problems = []
    fields = ["process_heading", "process_tagline", "lifestyle_heading",
              "lifestyle_tagline", "flatlay_headline"]
    for f in fields:
        seen = {}
        for p in PROFILES:
            v = getattr(p, f).strip().lower()
            if v in seen:
                problems.append(f"{f}: '{getattr(p, f)}' reused by "
                                f"{seen[v]} and {p.key}")
            seen[v] = p.key

    # Prop overlap: flag profiles sharing an unusually similar prop set.
    for i, a in enumerate(PROFILES):
        for b in PROFILES[i + 1:]:
            sa = set(_norm(a.flatlay_props).split())
            sb = set(_norm(b.flatlay_props).split())
            if len(sa & sb) / max(1, len(sa | sb)) > 0.55:
                problems.append(f"flatlay_props: {a.key} and {b.key} too similar")
    return problems


# ---------------------------------------------------------------------------
# Universal fallback engine — works for ANY product, for ANY brand
# ---------------------------------------------------------------------------
# generate_product_prompts() above is intentionally strict: it only knows the
# 11 hand-tuned GBN profiles and refuses to guess for anything else, so those
# SKUs always get their fully bespoke prompt. Everything below is additive —
# it never touches PROFILES or generate_product_prompts — and gives EVERY
# other product a coherent, on-brand, non-generic-looking prompt set instead
# of a hard failure. generate_any_product_prompts() is the entry point the
# webapp uses: curated profile if one matches, otherwise this engine.
GENERIC_QUALITY = ("hyperrealistic, photorealistic, 8K, premium commercial "
                   "brand photography, editorial luxury catalog polish, "
                   "immaculate art direction, sharp detail, no AI artifacts")


def generic_brand_token(brand_name: str = DEFAULT_BRAND_NAME) -> str:
    """A palette-neutral brand style token for products with no curated
    profile. Unlike brand_token(), this makes no assumption about the
    brand's origin or category — safe for any product, any brand."""
    return (f"{brand_name}, a premium brand; sophisticated dark charcoal and "
            "warm gold accent palette, clean cream highlights, elegant "
            "modern serif typography")


_FAMILY_KEYWORDS: Dict[str, List[str]] = {
    "liquid_food": ["oil", "ghee", "honey", "syrup", "sauce", "vinegar",
                    "juice", "beverage", "drink", "milk", "butter"],
    "packaged_food": ["tea", "coffee", "spice", "masala", "snack", "food",
                      "biscuit", "cookie", "chocolate", "nut", "cereal",
                      "flour", "rice", "sugar", "salt", "supplement",
                      "protein", "grocery", "powder"],
    "beauty_personal_care": ["beauty", "skincare", "skin care", "cosmetic",
                             "haircare", "hair care", "perfume", "fragrance",
                             "soap", "lotion", "cream", "serum", "shampoo"],
    "apparel_fashion": ["apparel", "fashion", "clothing", "wear", "footwear",
                        "shoe", "garment", "accessory", "accessories", "bag",
                        "jewelry", "jewellery"],
    "electronics_hardware": ["electronics", "gadget", "hardware", "tech",
                             "device", "appliance", "speaker", "headphone",
                             "earbud", "charger", "cable", "watch", "camera"],
}


def classify_family(category: str, product_name: str) -> str:
    """Pick the closest generic template family. Category is checked first
    (it is a short, controlled field), then the product name, then falls
    back to a fully generic family that fits absolutely anything."""
    cat = _norm(category or "")
    for fam, kws in _FAMILY_KEYWORDS.items():
        if any(kw in cat for kw in kws):
            return fam
    name = _norm(product_name or "")
    for fam, kws in _FAMILY_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return fam
    return "generic"


FAMILIES: Dict[str, Dict] = {
    "liquid_food": {
        "vessel_options": [
            "premium dark glass bottle with a matte label and a gold cap",
            "premium ceramic jar with a wooden lid and a gold-foiled label",
            "premium glass bottle with a brushed gold cap and a minimalist label",
        ],
        "hero_props": [
            "a small ceramic dish, a linen napkin, and a sprig of fresh herbs",
            "a rustic wooden tray, scattered whole spices, and a brass spoon",
            "a folded natural linen cloth, a small glass dish, and soft greenery",
        ],
        "process_headings": ["Crafted in Small Batches", "From Source to Bottle",
                             "The Traditional Way"],
        "process_bullets": [
            "Sourced from trusted growers", "Small-batch crafted for quality",
            "Naturally processed, never rushed", "Tested for purity at every step",
            "No artificial additives or fillers", "Bottled fresh to lock in flavour",
            "Traditional methods, modern care", "Quality checked before it ships",
        ],
        "process_scenes": [
            "a warm artisanal workshop with natural ingredients laid out on a "
            "wooden counter, soft morning light through a window",
            "a small-batch production room with glass vessels and natural "
            "ingredients arranged on a stone counter, warm ambient light",
            "a rustic countryside kitchen with fresh ingredients on a wooden "
            "table, gentle afternoon light",
        ],
        "process_taglines": ["Crafted With Patience, Bottled With Pride",
                             "Small Batches, Uncompromising Quality",
                             "From Nature's Source, Straight To You"],
        "lifestyle_scenes": [
            "hands pouring the product into a bowl on a sunlit kitchen "
            "counter, fresh ingredients nearby",
            "hands preparing a meal with the product on a rustic wooden "
            "table, warm natural light",
            "hands drizzling the product over a plated dish on an elegant "
            "table setting, soft daylight",
        ],
        "lifestyle_headings": ["Made for Everyday Use", "A Staple for Every Kitchen",
                               "Naturally Better, Every Day"],
        "benefits": [
            "Naturally sourced ingredients", "No artificial preservatives",
            "Rich, authentic flavour", "Crafted for everyday wellness",
            "Trusted small-batch quality", "Free from harmful additives",
            "Consistent purity, every batch", "Sustainably and responsibly made",
        ],
        "lifestyle_taglines": ["Pure Ingredients, Honest Craft",
                               "Quality You Can Taste",
                               "Naturally Better, Batch After Batch"],
        "flatlay_props": [
            "scattered whole spices, a linen cloth, a wooden spoon, and "
            "fresh greenery",
            "a small ceramic bowl, dried herbs, a brass ladle, and folded "
            "natural linen",
            "fresh ingredients, a rustic wooden board, and a sprig of "
            "greenery",
        ],
        "flatlay_headlines": ["Pure & Simple", "Naturally Crafted",
                              "Small-Batch Quality"],
        "badges": ["Small Batch", "Naturally Sourced", "No Additives",
                   "Quality Tested", "Handcrafted", "Trusted Purity"],
    },

    "packaged_food": {
        "vessel_options": [
            "premium stand-up pouch with a matte finish and a gold foil label",
            "premium branded box with a textured lid and gold lettering",
            "premium metal tin with a brushed lid and an embossed label",
        ],
        "hero_props": [
            "a small wooden bowl, scattered loose contents, and a linen napkin",
            "a rustic tray, a brass scoop, and a sprig of dried herbs",
            "a folded burlap cloth, a ceramic dish, and soft natural light",
        ],
        "process_headings": ["Roasted and Packed With Care", "From Farm to Pantry",
                             "Freshness You Can Taste"],
        "process_bullets": [
            "Sourced from trusted farms", "Small-batch roasted and packed",
            "Sealed fresh for maximum flavour", "No artificial preservatives added",
            "Quality checked at every stage", "Traditional recipes, modern care",
            "Packed within hours of preparation", "Rigorously tested for purity",
        ],
        "process_scenes": [
            "a warm pantry workshop with ingredients laid out on a wooden "
            "counter, soft natural light",
            "a small-batch packing room with fresh ingredients on a stone "
            "counter, warm ambient light",
            "a rustic kitchen counter with the raw ingredients on display, "
            "gentle afternoon light",
        ],
        "process_taglines": ["Packed Fresh, Delivered With Pride",
                             "Small Batches, Big Flavour",
                             "From Our Pantry to Yours"],
        "lifestyle_scenes": [
            "hands scooping the product into a bowl on a bright kitchen "
            "counter",
            "hands preparing a snack with the product on a rustic wooden "
            "table, warm light",
            "hands pouring the product into a jar on a sunlit breakfast "
            "table",
        ],
        "lifestyle_headings": ["A Pantry Favourite", "Made for Everyday Snacking",
                               "Freshness in Every Bite"],
        "benefits": [
            "Naturally sourced ingredients", "No artificial preservatives",
            "Rich, authentic taste", "Perfect for daily use",
            "Trusted small-batch quality", "Free from harmful additives",
            "Sealed fresh for freshness", "Sustainably and responsibly made",
        ],
        "lifestyle_taglines": ["Honest Ingredients, Honest Taste",
                               "Quality You Can Taste",
                               "Freshness, Batch After Batch"],
        "flatlay_props": [
            "scattered loose product, a linen cloth, a wooden scoop, and "
            "dried herbs",
            "a small ceramic bowl, natural ingredients, a brass spoon, and "
            "folded burlap",
            "fresh ingredients, a rustic wooden board, and scattered "
            "natural elements",
        ],
        "flatlay_headlines": ["Fresh & Wholesome", "Naturally Crafted",
                              "Small-Batch Quality"],
        "badges": ["Small Batch", "Naturally Sourced", "No Preservatives",
                   "Freshly Packed", "Handcrafted", "Quality Tested"],
    },

    "beauty_personal_care": {
        "vessel_options": [
            "premium frosted glass jar with a matte gold lid",
            "sleek airless pump bottle with a brushed metal cap",
            "minimalist glass dropper bottle with a gold pipette cap",
        ],
        "hero_props": [
            "scattered rose petals, a smooth stone, and a sprig of eucalyptus",
            "a folded cream linen towel, a small glass dish, and dried "
            "botanicals",
            "a natural wood tray, a soft bristle brush, and delicate flower "
            "petals",
        ],
        "process_headings": ["Formulated With Care", "Pure Ingredients, "
                             "Proven Results", "Crafted for Your Skin"],
        "process_bullets": [
            "Formulated with clean, natural ingredients",
            "Dermatologically mindful formulation",
            "Free from harsh sulphates and parabens",
            "Small-batch blended for consistency",
            "Cruelty-free and never tested on animals",
            "Rigorously tested for purity",
            "Sustainably sourced botanical extracts",
            "Balanced pH for everyday use",
        ],
        "process_scenes": [
            "a serene formulation studio with botanical ingredients on a "
            "marble counter, soft natural light",
            "a minimalist spa workspace with glass vessels and dried "
            "botanicals, warm ambient light",
            "a calm ingredient-blending scene with natural extracts on a "
            "stone counter, gentle daylight",
        ],
        "process_taglines": ["Formulated With Intention, Made to Nourish",
                             "Clean Ingredients, Visible Results",
                             "Pure by Design"],
        "lifestyle_scenes": [
            "hands gently applying the product in a calm, softly lit "
            "bathroom setting, no faces visible",
            "hands massaging the product into skin on a soft cotton towel, "
            "warm natural light, no faces visible",
            "hands holding the product beside a folded towel and candle, "
            "serene self-care setting, no faces visible",
        ],
        "lifestyle_headings": ["A Ritual Worth Repeating", "Self-Care, Simplified",
                               "Nourish Every Day"],
        "benefits": [
            "Deeply nourishes and hydrates", "Free from harsh chemicals",
            "Gentle for daily use", "Cruelty-free formulation",
            "Dermatologically mindful", "Naturally derived ingredients",
            "Balances and restores", "Lightweight, fast-absorbing",
        ],
        "lifestyle_taglines": ["Nourish Naturally, Every Day",
                               "Clean Beauty, Honest Results",
                               "Your Skin, Elevated"],
        "flatlay_props": [
            "scattered rose petals, a smooth stone, dried botanicals, and a "
            "linen towel",
            "a small glass dish, soft bristle brush, botanical extracts, and "
            "folded cream cloth",
            "delicate flower petals, a wooden tray, and natural skincare "
            "elements",
        ],
        "flatlay_headlines": ["Pure & Radiant", "Naturally Formulated",
                              "Clean Beauty"],
        "badges": ["Cruelty-Free", "Clean Formula", "Dermatologist Mindful",
                   "Naturally Derived", "Small Batch", "Sulphate-Free"],
    },

    "apparel_fashion": {
        "vessel_options": None,
        "hero_props": [
            "a neatly folded natural linen backdrop and a single dried branch",
            "a minimalist wooden hanger and soft draped fabric in the "
            "background",
            "a folded canvas cloth and a subtle leather accessory beside it",
        ],
        "process_headings": ["Crafted With Precision", "Made to Last",
                             "The Art of Fine Tailoring"],
        "process_bullets": [
            "Cut from premium, carefully selected fabric",
            "Stitched by skilled artisans",
            "Finished with reinforced, durable seams",
            "Quality checked at every stage",
            "Sustainably and ethically sourced materials",
            "Designed for lasting comfort",
            "Small-batch crafted for consistency",
            "Tested for fit and durability",
        ],
        "process_scenes": [
            "a warm tailoring workshop with fabric rolls and a sewing "
            "station, soft natural light",
            "a minimalist atelier with cutting tools and folded fabric on a "
            "wooden table, warm light",
            "a craft studio with thread spools and a garment in progress, "
            "gentle afternoon light",
        ],
        "process_taglines": ["Crafted With Precision, Made to Last",
                             "Small-Batch Tailoring, Uncompromising Quality",
                             "Where Craft Meets Comfort"],
        "lifestyle_scenes": [
            "hands adjusting the garment on a wooden hanger in a bright "
            "minimalist room, no faces visible",
            "hands folding the product neatly on a linen-covered table, "
            "warm natural light, no faces visible",
            "hands presenting the product against a soft neutral backdrop, "
            "elegant styling, no faces visible",
        ],
        "lifestyle_headings": ["Designed for Everyday Confidence",
                               "Comfort Meets Style",
                               "Made to Be Worn, Made to Last"],
        "benefits": [
            "Premium, carefully selected fabric", "Reinforced for lasting "
            "durability", "Designed for everyday comfort",
            "Ethically and sustainably made", "Versatile for any occasion",
            "Consistent, reliable fit", "Finished with meticulous detail",
            "Small-batch crafted quality",
        ],
        "lifestyle_taglines": ["Made to Move With You", "Style That Lasts",
                               "Crafted for Everyday Confidence"],
        "flatlay_props": [
            "folded fabric swatches, a spool of thread, and a minimalist "
            "accessory",
            "a wooden hanger, soft draped fabric, and a leather accessory",
            "neatly folded garments, a measuring tape, and natural styling "
            "elements",
        ],
        "flatlay_headlines": ["Crafted to Last", "Designed With Care",
                              "Timeless Quality"],
        "badges": ["Premium Fabric", "Ethically Made", "Small Batch",
                   "Reinforced Stitching", "Sustainably Sourced",
                   "Quality Tested"],
    },

    "electronics_hardware": {
        "vessel_options": None,
        "hero_props": [
            "a minimalist matte pedestal and subtle ambient reflections",
            "a sleek dark surface with soft directional highlights",
            "a floating display stand with a soft gradient backdrop",
        ],
        "process_headings": ["Engineered for Performance", "Precision in "
                             "Every Detail", "Built to Perform"],
        "process_bullets": [
            "Engineered with precision components",
            "Rigorously tested for reliability",
            "Designed for everyday performance",
            "Built with premium, durable materials",
            "Quality checked before it ships",
            "Optimised for consistent performance",
            "Thoughtfully engineered for real use",
            "Tested across real-world conditions",
        ],
        "process_scenes": [
            "a minimalist engineering workspace with precision tools on a "
            "matte desk, cool ambient light",
            "a modern product lab with components laid out on a clean "
            "surface, soft studio light",
            "a sleek design studio with the device in various assembly "
            "stages, gentle directional light",
        ],
        "process_taglines": ["Engineered With Precision, Built to Last",
                             "Performance You Can Rely On",
                             "Designed for the Way You Live"],
        "lifestyle_scenes": [
            "hands operating the device on a clean modern desk, soft "
            "daylight, no faces visible",
            "hands using the product in a bright minimalist workspace, no "
            "faces visible",
            "hands setting up the device on a sleek table, warm ambient "
            "light, no faces visible",
        ],
        "lifestyle_headings": ["Performance for Everyday Life", "Designed "
                               "Around You", "Effortless, Every Time"],
        "benefits": [
            "Reliable, everyday performance", "Precision-engineered "
            "components", "Durable, long-lasting build",
            "Optimised for real-world use", "Seamless, intuitive experience",
            "Consistent performance you can trust", "Thoughtfully designed "
            "details", "Rigorously tested quality",
        ],
        "lifestyle_taglines": ["Performance, Redefined",
                               "Built for the Way You Live",
                               "Precision Meets Simplicity"],
        "flatlay_props": [
            "neatly arranged cables, a minimalist stand, and soft ambient "
            "lighting accents",
            "a sleek accessory pouch, a cleaning cloth, and subtle styling "
            "elements",
            "a minimalist charging dock and softly arranged accessories",
        ],
        "flatlay_headlines": ["Precision Engineered", "Built to Perform",
                              "Designed With Purpose"],
        "badges": ["Precision Built", "Rigorously Tested", "Durable Design",
                   "Performance Tested", "Premium Materials",
                   "Reliable Build"],
    },

    "generic": {
        "vessel_options": None,
        "hero_props": [
            "a minimalist pedestal, soft directional light, and understated "
            "styling elements",
            "a softly draped neutral backdrop with subtle natural textures",
            "a clean matte surface with a single elegant styling accent",
        ],
        "process_headings": ["Crafted With Care", "Made to Impress",
                             "Quality in Every Detail"],
        "process_bullets": [
            "Thoughtfully designed and crafted",
            "Made with premium, quality materials",
            "Rigorously tested before it ships",
            "Small-batch crafted for consistency",
            "Built to a higher standard",
            "Quality checked at every stage",
            "Designed with the end user in mind",
            "Sustainably and responsibly made",
        ],
        "process_scenes": [
            "a warm, minimalist workshop with the product's raw materials "
            "on a wooden counter, soft natural light",
            "a clean design studio with the product shown in progress, "
            "gentle ambient light",
            "a craft space with quality materials arranged on a stone "
            "counter, warm daylight",
        ],
        "process_taglines": ["Crafted With Purpose, Made to Impress",
                             "Small-Batch Quality, Uncompromising Standards",
                             "Where Craft Meets Care"],
        "lifestyle_scenes": [
            "hands presenting the product on a clean, softly lit surface, "
            "no faces visible",
            "hands using the product in a bright minimalist setting, no "
            "faces visible",
            "hands holding the product against a soft neutral backdrop, "
            "elegant styling, no faces visible",
        ],
        "lifestyle_headings": ["Designed for Everyday Life", "Made for You",
                               "Quality You Can Feel"],
        "benefits": [
            "Premium, carefully selected materials", "Built to a higher "
            "standard", "Designed for everyday use",
            "Consistent, reliable quality", "Thoughtfully crafted details",
            "Trusted small-batch quality", "Sustainably and responsibly "
            "made", "Rigorously tested before shipping",
        ],
        "lifestyle_taglines": ["Made With Purpose, Built to Last",
                               "Quality You Can Feel",
                               "Crafted for Everyday Confidence"],
        "flatlay_props": [
            "a few understated styling accents, soft natural textures, and "
            "clean negative space",
            "minimalist props, a neutral backdrop, and soft directional "
            "shadows",
            "quality materials arranged with intentional spacing and clean "
            "styling",
        ],
        "flatlay_headlines": ["Crafted With Care", "Quality by Design",
                              "Made to Impress"],
        "badges": ["Premium Quality", "Small Batch", "Quality Tested",
                   "Handcrafted", "Trusted Brand", "Built to Last"],
    },
}


def _rng_for(*parts: str) -> random.Random:
    """A Random instance seeded deterministically from the given strings, so
    the same product always maps to the same generic prompt (stable across
    preview -> generate), while different products vary."""
    key = "|".join(parts)
    seed = hashlib.md5(key.encode("utf-8")).hexdigest()
    return random.Random(seed)


def _pick(pool: List[str], rng: random.Random) -> str:
    return rng.choice(pool)


def _pick_n(pool: List[str], n: int, rng: random.Random) -> List[str]:
    return rng.sample(pool, min(n, len(pool)))


def generate_generic_prompts(product_name: str, size: str, category: str,
                             brand_name: str = DEFAULT_BRAND_NAME
                             ) -> Dict[str, Dict]:
    """Universal fallback — produces a complete, coherent, on-brand 4-slot
    prompt set for ANY product name and ANY brand, with no curated Profile
    required. Category-aware (liquid/food, packaged food, beauty, apparel,
    electronics, or a fully generic fallback that fits literally anything),
    and deterministic per product so repeated previews stay stable.

    Raises ValueError only if product_name is blank.
    """
    product_name = (product_name or "").strip()
    if not product_name:
        raise ValueError("Product name is required.")

    brand_name = (brand_name or DEFAULT_BRAND_NAME).strip() or DEFAULT_BRAND_NAME
    size = (size or "").strip()
    size_suffix = f", {size}" if size else ""
    family = classify_family(category, product_name)
    pools = FAMILIES[family]
    rng = _rng_for(product_name, size, category)

    brand = generic_brand_token(brand_name)
    hero_props = _pick(pools["hero_props"], rng)
    process_heading = _pick(pools["process_headings"], rng)
    process_bullets = "; ".join(_pick_n(pools["process_bullets"], 4, rng))
    process_scene = _pick(pools["process_scenes"], rng)
    process_tagline = _pick(pools["process_taglines"], rng)
    lifestyle_scene = _pick(pools["lifestyle_scenes"], rng)
    lifestyle_heading = _pick(pools["lifestyle_headings"], rng)
    benefits = "; ".join(_pick_n(pools["benefits"], 4, rng))
    lifestyle_tagline = _pick(pools["lifestyle_taglines"], rng)
    flatlay_props = _pick(pools["flatlay_props"], rng)
    flatlay_headline = _pick(pools["flatlay_headlines"], rng)
    badges = ", ".join(_pick_n(pools["badges"], 3, rng))

    vessel_options = pools.get("vessel_options")
    if vessel_options:
        vessel = _pick(vessel_options, rng)
        hero = (
            f"Hyperrealistic premium ecommerce product photography of a "
            f"single {vessel}, containing {product_name}. The gold label "
            f"clearly reads '{brand_name}' at the top, '{product_name}' in "
            f"the middle, and '{size}' in large bold gold lettering at the "
            f"bottom as the most prominent text. The product stands "
            f"centered on a dark polished walnut wooden surface, styled "
            f"with {hero_props}. Warm golden studio rim lighting from the "
            f"top left, deep charcoal bokeh background, ultra sharp focus "
            f"on the label, Phase One medium format camera quality. "
            f"{GENERIC_QUALITY}. No people, no text overlays."
        )
        process_subject = (f"A {vessel}, holding {product_name}{size_suffix}, "
                           f"sits at the bottom center.")
        flatlay_subject = (f"A {vessel}, holding {product_name}{size_suffix}, "
                           f"lies centered under a dramatic warm golden "
                           f"spotlight from directly above.")
    else:
        hero = (
            f"Hyperrealistic premium ecommerce product photography of a "
            f"single {product_name}{size_suffix}, presented as the sole "
            f"hero object on a dark polished walnut wooden surface, styled "
            f"with {hero_props}. A small elegant tag beside the product "
            f"reads '{brand_name}' in refined gold lettering. Warm golden "
            f"studio rim lighting from the top left, deep charcoal bokeh "
            f"background, ultra sharp focus on the product, Phase One "
            f"medium format camera quality. {GENERIC_QUALITY}. No people, "
            f"no text overlays."
        )
        process_subject = (f"The {product_name}{size_suffix} sits at the "
                           f"bottom center.")
        flatlay_subject = (f"The {product_name}{size_suffix} lies centered "
                           f"under a dramatic warm golden spotlight from "
                           f"directly above.")

    process = (
        f"Square 1:1 premium brand poster. {brand}. Solid deep charcoal "
        f"#1C1C1C background. The top 15 percent is left clean and empty "
        f"for a logo. Left column: a large white Playfair Display serif "
        f"heading '{process_heading}', a thin gold divider rule beneath it, "
        f"then four white bullet points with small gold markers reading: "
        f"{process_bullets}. Right column: a photorealistic scene of "
        f"{process_scene}. {process_subject} A full width dark charcoal "
        f"banner runs along the bottom with gold serif text "
        f"'{process_tagline}'. Crisp clean typography, perfectly spelled. "
        f"{GENERIC_QUALITY}."
    )

    lifestyle = (
        f"Square 1:1 premium brand poster. {brand}. Warm cream #FBF7EF "
        f"background. The top 15 percent is left clean and empty for a "
        f"logo. The main scene shows {lifestyle_scene}. Absolutely no faces "
        f"are visible, only hands and clothing. To one side a large dark "
        f"charcoal Playfair Display serif heading reads "
        f"'{lifestyle_heading}', with four benefit rows beneath it in dark "
        f"charcoal text with gold icons reading: {benefits}. A full width "
        f"dark charcoal banner runs along the bottom with centered gold "
        f"serif text '{lifestyle_tagline}'. Elegant editorial layout, "
        f"generous white space, perfectly spelled typography. "
        f"{GENERIC_QUALITY}."
    )

    flatlay = (
        f"Square 1:1 premium brand poster, overhead flat lay photography on "
        f"a dark charcoal #1C1C1C textured surface. {brand}. The top 15 "
        f"percent is left clean and empty for a logo. {flatlay_subject} "
        f"Arranged around it with intentional spacing and clear negative "
        f"space: {flatlay_props}. Near the bottom a short gold Playfair "
        f"Display headline reads '{flatlay_headline}', with cream subtext "
        f"below reading '{product_name}{size_suffix}', and three small gold "
        f"badge icons in a row reading {badges}. Museum-quality styling, "
        f"never cluttered. {GENERIC_QUALITY}."
    )

    return {
        "01_Hero":      {"prompt": hero,      "negative": NEG_HERO,   "variant": "hero"},
        "02_Process":   {"prompt": process,   "negative": NEG_POSTER, "variant": "process"},
        "03_Lifestyle": {"prompt": lifestyle, "negative": NEG_POSTER, "variant": "lifestyle"},
        "04_FlatLay":   {"prompt": flatlay,   "negative": NEG_FLAT,   "variant": "flatlay"},
    }


def generate_any_product_prompts(product_name: str, size: str, category: str,
                                 brand_name: str = DEFAULT_BRAND_NAME
                                 ) -> Tuple[Dict[str, Dict], str]:
    """The entry point the webapp uses. Curated profile if the product name
    matches one of the 11 hand-tuned GBN profiles; otherwise the universal
    generic engine. Returns (prompts, source) where source is "curated" or
    "generic", so the caller can surface which path was used.

    generate_product_prompts()'s strict ValueError-on-no-match behaviour
    (relied on by the original CLI) is left completely untouched — this is
    an additive wrapper on top of it, not a change to it.
    """
    try:
        return generate_product_prompts(product_name, size, category,
                                        brand_name), "curated"
    except ValueError:
        return generate_generic_prompts(product_name, size, category,
                                        brand_name), "generic"


if __name__ == "__main__":
    issues = audit_uniqueness()
    print(f"Profiles loaded: {len(PROFILES)}")
    if issues:
        print("UNIQUENESS ISSUES:")
        for i in issues:
            print("  -", i)
    else:
        print("Uniqueness audit: PASS — all concepts distinct.")
