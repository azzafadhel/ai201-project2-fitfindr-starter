"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings


# Load .env explicitly from the project root.
# This avoids issues when Python is run through standard input.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 400,
) -> str:
    """
    Call Groq and return a non-empty response string.

    The public tools catch API errors and return useful fallback responses.
    """
    client = _get_groq_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError("The LLM returned an empty response.")

    return content.strip()


# ── Shared helper functions ───────────────────────────────────────────────────

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "i",
    "in",
    "is",
    "it",
    "looking",
    "me",
    "my",
    "of",
    "or",
    "the",
    "to",
    "under",
    "want",
    "with",
}


def _tokenize(value: Any) -> set[str]:
    """Convert text or a list of values into lowercase search keywords."""
    if value is None:
        return set()

    if isinstance(value, list):
        value = " ".join(str(item) for item in value)

    words = set(re.findall(r"[a-z0-9]+", str(value).lower()))

    return {
        word
        for word in words
        if word not in _STOP_WORDS
    }


def _normalize_requested_size(size: str) -> str:
    """Normalize common size names such as 'medium' to 'M'."""
    normalized = size.strip().upper()

    aliases = {
        "EXTRA SMALL": "XS",
        "X-SMALL": "XS",
        "X SMALL": "XS",
        "SMALL": "S",
        "MEDIUM": "M",
        "LARGE": "L",
        "EXTRA LARGE": "XL",
        "X-LARGE": "XL",
        "X LARGE": "XL",
        "2XL": "XXL",
        "ONE-SIZE": "ONE SIZE",
        "ONESIZE": "ONE SIZE",
    }

    return aliases.get(normalized, normalized)


def _size_matches(
    requested_size: str | None,
    listing_size: Any,
) -> bool:
    """
    Check whether a requested size matches a listing size.

    Examples:
        M matches M
        M matches S/M
        M matches M/L
        XL matches XL (oversized)
        W30 matches W30 L30
        US 8 matches US 8
    """
    if requested_size is None or not str(requested_size).strip():
        return True

    if listing_size is None:
        return False

    requested = _normalize_requested_size(str(requested_size))
    listed = str(listing_size).strip().upper()

    # Handle letter sizes without accidentally reading the L in "L30"
    # as clothing size Large.
    letter_sizes = set(
        re.findall(
            r"(?<![A-Z0-9])(XXL|XXS|XL|XS|S|M|L)(?![A-Z0-9])",
            listed,
        )
    )

    if requested in {"XXS", "XS", "S", "M", "L", "XL", "XXL"}:
        return requested in letter_sizes

    compact_requested = re.sub(r"\s+", "", requested)
    compact_listed = re.sub(r"\s+", "", listed)

    # Waist and length measurements, such as W30 or L30.
    if re.fullmatch(r"[WL]\d+(?:\.\d+)?", compact_requested):
        listing_measurements = set(
            re.findall(r"[WL]\d+(?:\.\d+)?", compact_listed)
        )
        return compact_requested in listing_measurements

    # Shoe sizes, such as US 8 or US 8.5.
    if re.fullmatch(r"US\d+(?:\.\d+)?", compact_requested):
        listing_shoe_sizes = {
            re.sub(r"\s+", "", result)
            for result in re.findall(
                r"US\s*\d+(?:\.\d+)?",
                listed,
            )
        }
        return compact_requested in listing_shoe_sizes

    # Allow a request like "8" to match a listing marked "US 8".
    if re.fullmatch(r"\d+(?:\.\d+)?", compact_requested):
        shoe_numbers = re.findall(
            r"US\s*(\d+(?:\.\d+)?)",
            listed,
        )
        return compact_requested in shoe_numbers

    if requested == "ONE SIZE":
        return "ONE SIZE" in listed

    return compact_requested == compact_listed


def _score_listing(
    listing: dict,
    query_words: set[str],
) -> int:
    """
    Score a listing using weighted keyword overlap.

    Matches in the title and style tags receive more weight because they
    usually describe the item more directly.
    """
    field_weights = {
        "title": 5,
        "style_tags": 4,
        "category": 3,
        "description": 2,
        "colors": 1,
        "brand": 1,
    }

    score = 0

    for field, weight in field_weights.items():
        field_words = _tokenize(listing.get(field))
        overlap = query_words.intersection(field_words)
        score += len(overlap) * weight

    return score


def _format_item_for_prompt(item: dict) -> str:
    """Format relevant listing information for an LLM prompt."""
    item_fields = {
        "title": item.get("title"),
        "description": item.get("description"),
        "category": item.get("category"),
        "style_tags": item.get("style_tags", []),
        "size": item.get("size"),
        "condition": item.get("condition"),
        "price": item.get("price"),
        "colors": item.get("colors", []),
        "brand": item.get("brand"),
        "platform": item.get("platform"),
    }

    return json.dumps(
        item_fields,
        indent=2,
        ensure_ascii=False,
    )


# ── Fallback responses ────────────────────────────────────────────────────────

def _general_outfit_fallback(new_item: dict) -> str:
    """Return general styling advice when the wardrobe is empty."""
    item_name = new_item.get("title", "this thrifted item")
    category = str(new_item.get("category", "")).lower()

    recommendations = {
        "tops": (
            "relaxed jeans and neutral sneakers",
            "The simple base keeps attention on the top.",
        ),
        "bottoms": (
            "a fitted neutral top and simple sneakers",
            "The fitted top balances the shape of the bottoms.",
        ),
        "outerwear": (
            "a basic tee, straight-leg jeans, and ankle boots",
            "The simple layers allow the outerwear to remain the focus.",
        ),
        "shoes": (
            "straight-leg jeans and a neutral top",
            "The clean base lets the shoes become the main detail.",
        ),
        "accessories": (
            "a neutral top, relaxed jeans, and simple shoes",
            "The neutral outfit makes the accessory feel intentional.",
        ),
    }

    pieces, explanation = recommendations.get(
        category,
        (
            "relaxed jeans, a neutral top, and simple sneakers",
            "The neutral basics create an easy outfit around the item.",
        ),
    )

    return (
        "Your saved wardrobe is empty, so these are general recommendations "
        f"rather than items you already own. Style the {item_name} with "
        f"{pieces}. {explanation}"
    )


def _wardrobe_outfit_fallback(
    new_item: dict,
    wardrobe_items: list[dict],
) -> str:
    """Build a basic outfit using actual wardrobe items if Groq fails."""
    item_name = new_item.get("title", "this thrifted item")
    new_category = str(new_item.get("category", "")).lower()

    preferred_categories = {
        "tops": ["bottoms", "shoes", "outerwear", "accessories"],
        "bottoms": ["tops", "shoes", "outerwear", "accessories"],
        "outerwear": ["tops", "bottoms", "shoes", "accessories"],
        "shoes": ["bottoms", "tops", "outerwear", "accessories"],
        "accessories": ["tops", "bottoms", "shoes", "outerwear"],
    }

    category_order = preferred_categories.get(
        new_category,
        ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    )

    selected_items: list[dict] = []

    for wanted_category in category_order:
        for wardrobe_item in wardrobe_items:
            if wardrobe_item in selected_items:
                continue

            if wardrobe_item.get("category") == wanted_category:
                selected_items.append(wardrobe_item)
                break

        if len(selected_items) >= 3:
            break

    if not selected_items:
        selected_items = wardrobe_items[:2]

    item_names = [
        item.get("name", "wardrobe item")
        for item in selected_items
    ]

    if not item_names:
        return _general_outfit_fallback(new_item)

    if len(item_names) == 1:
        pieces_text = item_names[0]
    else:
        pieces_text = ", ".join(item_names[:-1])
        pieces_text += f", and {item_names[-1]}"

    return (
        f"Pair the {item_name} with your {pieces_text}. "
        "Keep the styling simple so the thrifted item remains the focus. "
        "A small tuck or light layer can add shape to the outfit."
    )


def _fit_card_fallback(outfit: str, new_item: dict) -> str:
    """Create a template-based caption if the Groq request fails."""
    item_name = new_item.get("title", "Thrifted find")
    platform = new_item.get("platform", "a secondhand platform")
    price = new_item.get("price")

    if isinstance(price, (int, float)):
        price_text = f"${price:.2f}"
    else:
        price_text = "price unavailable"

    clean_outfit = " ".join(outfit.split())

    if len(clean_outfit) > 180:
        clean_outfit = clean_outfit[:177].rstrip() + "..."

    return (
        f"Considering the {item_name} from {platform} for {price_text}. "
        f"{clean_outfit} An easy secondhand look worth saving."
    )


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    if not isinstance(description, str) or not description.strip():
        return []

    query_words = _tokenize(description)

    if not query_words:
        return []

    if max_price is not None:
        try:
            price_limit = float(max_price)
        except (TypeError, ValueError):
            return []

        if price_limit < 0:
            return []
    else:
        price_limit = None

    try:
        listings = load_listings()
    except Exception:
        # The required failure behavior is to return an empty list.
        return []

    scored_results: list[tuple[int, float, dict]] = []

    for listing in listings:
        try:
            listing_price = float(listing["price"])
        except (KeyError, TypeError, ValueError):
            continue

        # Apply the optional maximum-price filter.
        if price_limit is not None and listing_price > price_limit:
            continue

        # Apply the optional size filter.
        if not _size_matches(size, listing.get("size")):
            continue

        score = _score_listing(listing, query_words)

        # Do not return unrelated listings.
        if score <= 0:
            continue

        scored_results.append(
            (
                score,
                listing_price,
                listing,
            )
        )

    # Higher relevance first. Lower price breaks equal-score ties.
    scored_results.sort(
        key=lambda result: (
            -result[0],
            result[1],
        )
    )

    return [
        listing
        for _, _, listing in scored_results
    ]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    if not isinstance(new_item, dict) or not new_item:
        return (
            "I couldn't create an outfit because the selected listing "
            "is missing."
        )

    if not new_item.get("title") or not new_item.get("category"):
        return (
            "I couldn't create an outfit because the selected listing "
            "does not contain enough item information."
        )

    if not isinstance(wardrobe, dict):
        wardrobe = {"items": []}

    wardrobe_items = wardrobe.get("items", [])

    if not isinstance(wardrobe_items, list):
        wardrobe_items = []

    item_text = _format_item_for_prompt(new_item)

    # Empty wardrobe: provide general styling recommendations.
    if not wardrobe_items:
        system_prompt = (
            "You are FitFindr, a helpful secondhand-fashion stylist. "
            "Give concise, wearable, and practical styling advice."
        )

        user_prompt = f"""
The user is considering this secondhand item:

{item_text}

The user's saved wardrobe is empty.

Suggest one complete outfit using common wardrobe basics. Clearly state that
the suggested pieces are general recommendations and are not items the user
already owns.

Include:
- the recommended clothing and shoes,
- the overall outfit vibe,
- one practical styling instruction,
- a brief explanation of why the combination works.

Keep the answer between 3 and 5 sentences.
""".strip()

        try:
            suggestion = _call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=300,
            )

            return (
                "Your saved wardrobe is empty, so these are general "
                f"recommendations rather than items you already own. {suggestion}"
            )

        except Exception:
            return _general_outfit_fallback(new_item)

    # Populated wardrobe: ask the LLM to use exact wardrobe items.
    wardrobe_text = json.dumps(
        wardrobe_items,
        indent=2,
        ensure_ascii=False,
    )

    system_prompt = (
        "You are FitFindr, a practical secondhand-fashion stylist. "
        "Use only wardrobe pieces that appear in the provided wardrobe data. "
        "Never invent an item and never claim the user owns an unlisted item."
    )

    user_prompt = f"""
The user is considering this secondhand item:

{item_text}

The user's existing wardrobe is:

{wardrobe_text}

Suggest one or two complete outfits that include the secondhand item.

Requirements:
- Refer to wardrobe pieces using their exact provided names.
- Use only pieces that appear in the wardrobe.
- Mention the outfit style or vibe.
- Include at least one useful styling instruction.
- Briefly explain why the colors, shapes, or styles work together.
- Keep the complete response between 4 and 7 sentences.
""".strip()

    try:
        return _call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.75,
            max_tokens=450,
        )

    except Exception:
        return _wardrobe_outfit_fallback(
            new_item=new_item,
            wardrobe_items=wardrobe_items,
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not isinstance(outfit, str) or not outfit.strip():
        return (
            "I couldn't create a fit card because the outfit suggestion "
            "is missing or empty."
        )

    if not isinstance(new_item, dict) or not new_item:
        return (
            "I couldn't create a fit card because the selected listing "
            "information is missing."
        )

    required_fields = ["title", "price", "platform"]

    missing_fields = [
        field
        for field in required_fields
        if new_item.get(field) in (None, "")
    ]

    if missing_fields:
        return (
            "I couldn't create a fit card because the selected listing "
            f"is missing: {', '.join(missing_fields)}."
        )

    item_text = _format_item_for_prompt(new_item)

    system_prompt = (
        "You write short and natural social-media captions for secondhand "
        "outfits. The tone should feel like a real OOTD post: casual, "
        "specific, and shareable rather than promotional."
    )

    user_prompt = f"""
Write a 2–4 sentence Instagram or TikTok outfit caption.

Secondhand item:
{item_text}

Outfit suggestion:
{outfit}

Requirements:
- Mention the exact item title naturally once.
- Mention the price naturally once.
- Mention the platform naturally once.
- Describe the outfit vibe using specific details from the outfit.
- Do not claim that the user already bought the item.
- Do not use a heading, quotation marks, or bullet points.
- One or two appropriate emojis are allowed.
- Avoid sounding like a product advertisement.
""".strip()

    try:
        return _call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=1.1,
            max_tokens=220,
        )

    except Exception:
        return _fit_card_fallback(
            outfit=outfit,
            new_item=new_item,
        )
