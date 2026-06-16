"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re
from typing import Any

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run.
    """
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "status": "started",
        "tool_trace": [],
    }


# ── query parsing helpers ─────────────────────────────────────────────────────

def _normalize_size(size: str) -> str:
    """Normalize size values extracted from a user query."""
    normalized = re.sub(r"\s+", " ", size.strip()).upper()

    aliases = {
        "EXTRA SMALL": "XS",
        "X-SMALL": "XS",
        "SMALL": "S",
        "MEDIUM": "M",
        "LARGE": "L",
        "EXTRA LARGE": "XL",
        "X-LARGE": "XL",
        "2XL": "XXL",
    }

    return aliases.get(normalized, normalized)


def _remove_match(text: str, match: re.Match[str]) -> str:
    """Remove one regex match from text while preserving surrounding content."""
    return text[:match.start()] + " " + text[match.end():]


def _clean_description(text: str) -> str:
    """Remove conversational filler and punctuation from a parsed description."""
    filler_patterns = [
        r"^\s*i(?:'m| am)?\s+looking\s+for\s+",
        r"^\s*looking\s+for\s+",
        r"^\s*(?:can you\s+)?find\s+me\s+",
        r"^\s*show\s+me\s+",
        r"^\s*i\s+want\s+",
        r"\bwhat(?:'s| is)\s+out\s+there\b.*$",
        r"\band\s+how\s+would\s+i\s+style\s+it\b.*$",
        r"\bhow\s+would\s+i\s+style\s+it\b.*$",
    ]

    cleaned = text

    for pattern in filler_patterns:
        cleaned = re.sub(
            pattern,
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"[,;:!?]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Remove an article left after conversational phrases such as
    # "I'm looking for a vintage graphic tee."
    cleaned = re.sub(
        r"^\s*(?:a|an|the)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip(" .-")




def _parse_query(query: str) -> dict[str, Any]:
    """
    Extract description, size, and maximum price using deterministic regex.

    Supported examples:
        vintage graphic tee under $30, size M
        90s track jacket in size M
        black combat boots size 8
        vintage jeans size W30 below $50
    """
    if not isinstance(query, str):
        return {
            "description": "",
            "size": None,
            "max_price": None,
        }

    working_text = query.strip()
    max_price = None
    size = None

    # Look first for phrases such as "under $30" or "up to 40".
    price_patterns = [
        (
            r"\b(?:under|below|less\s+than|up\s+to|"
            r"max(?:imum)?(?:\s+price)?(?:\s+of)?)"
            r"\s*\$?\s*(\d+(?:\.\d+)?)\b"
        ),
        r"\$\s*(\d+(?:\.\d+)?)\b",
    ]

    for pattern in price_patterns:
        match = re.search(
            pattern,
            working_text,
            flags=re.IGNORECASE,
        )

        if match:
            try:
                max_price = float(match.group(1))
            except (TypeError, ValueError):
                max_price = None

            working_text = _remove_match(working_text, match)
            break

    # Match sizes such as M, XXS, M/L, W30, US 8, or 8.
    size_pattern = (
        r"\b(?:in\s+)?size\s+("
        r"(?:US\s*)?\d+(?:\.\d+)?"
        r"|(?:XXS|XS|S|M|L|XL|XXL)"
        r"(?:/(?:XXS|XS|S|M|L|XL|XXL))?"
        r"|[WL]\d+(?:\.\d+)?"
        r")\b"
    )

    size_match = re.search(
        size_pattern,
        working_text,
        flags=re.IGNORECASE,
    )

    if size_match:
        size = _normalize_size(size_match.group(1))
        working_text = _remove_match(working_text, size_match)

    description = _clean_description(working_text)

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _format_price(price: float | None) -> str:
    """Format a price for a user-facing message."""
    if price is None:
        return ""

    return f"${price:g}"


def _no_results_message(parsed: dict) -> str:
    """Build a specific and actionable no-results message."""
    description = parsed.get("description") or "that item"
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    constraints = []

    if size:
        constraints.append(f"in size {size}")

    if max_price is not None:
        constraints.append(f"under {_format_price(max_price)}")

    constraint_text = " ".join(constraints)

    if constraint_text:
        search_text = f"'{description}' {constraint_text}"
    else:
        search_text = f"'{description}'"

    return (
        f"I couldn't find any listings for {search_text}. "
        "Try using a broader description, removing the size filter, "
        "or increasing the maximum price."
    )


def _is_outfit_error(result: str) -> bool:
    """Recognize an informative error string returned by suggest_outfit."""
    if not isinstance(result, str) or not result.strip():
        return True

    lowered = result.strip().lower()

    return (
        lowered.startswith("i couldn't create an outfit")
        or lowered.startswith("i could not create an outfit")
    )


def _is_fit_card_error(result: str) -> bool:
    """Recognize an informative error string returned by create_fit_card."""
    if not isinstance(result, str) or not result.strip():
        return True

    lowered = result.strip().lower()

    return (
        lowered.startswith("i couldn't create a fit card")
        or lowered.startswith("i could not create a fit card")
    )


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the FitFindr planning loop for one user interaction.

    The next tool is called only when the previous tool returned usable data.
    All intermediate data is stored in the session dictionary.
    """
    if not isinstance(wardrobe, dict):
        wardrobe = {"items": []}

    session = _new_session(query, wardrobe)

    # Step 1 and 2: validate and parse the query.
    if not isinstance(query, str) or not query.strip():
        session["status"] = "invalid_query"
        session["error"] = (
            "Please describe the secondhand item you are looking for. "
            "For example: 'vintage graphic tee under $30, size M.'"
        )
        return session

    parsed = _parse_query(query)
    session["parsed"] = parsed

    if not parsed["description"]:
        session["status"] = "invalid_query"
        session["error"] = (
            "I couldn't identify the item you want. Please include an item "
            "description such as 'graphic tee,' 'track jacket,' or 'boots.'"
        )
        return session

    if parsed["max_price"] is not None and parsed["max_price"] < 0:
        session["status"] = "invalid_query"
        session["error"] = (
            "The maximum price must be a positive number."
        )
        return session

    # Step 3: search.
    search_input = {
        "description": parsed["description"],
        "size": parsed["size"],
        "max_price": parsed["max_price"],
    }

    try:
        results = search_listings(**search_input)
    except Exception as exc:
        session["status"] = "search_error"
        session["error"] = (
            "I couldn't search the listings because the search tool failed. "
            f"Details: {exc}"
        )
        session["tool_trace"].append(
            {
                "tool": "search_listings",
                "input": search_input,
                "status": "error",
            }
        )
        return session

    if not isinstance(results, list):
        session["status"] = "search_error"
        session["error"] = (
            "The listing search returned an unexpected result, so I stopped "
            "before using unreliable data."
        )
        return session

    session["search_results"] = results
    session["tool_trace"].append(
        {
            "tool": "search_listings",
            "input": search_input,
            "status": "complete",
            "result_count": len(results),
        }
    )

    if not results:
        session["status"] = "no_results"
        session["error"] = _no_results_message(parsed)
        return session

    # Step 4: select the top-ranked result.
    selected_item = results[0]

    if not isinstance(selected_item, dict) or not selected_item:
        session["status"] = "selection_error"
        session["error"] = (
            "The search returned a result, but it did not contain valid "
            "listing information."
        )
        return session

    session["selected_item"] = selected_item
    session["status"] = "listing_selected"

    # Step 5: pass the exact selected-item object and wardrobe into Tool 2.
    try:
        outfit = suggest_outfit(
            session["selected_item"],
            session["wardrobe"],
        )
    except Exception as exc:
        session["status"] = "outfit_error"
        session["error"] = (
            "I found a listing, but I couldn't create an outfit suggestion. "
            f"Details: {exc}"
        )
        session["tool_trace"].append(
            {
                "tool": "suggest_outfit",
                "status": "error",
            }
        )
        return session

    session["tool_trace"].append(
        {
            "tool": "suggest_outfit",
            "input_item_id": session["selected_item"].get("id"),
            "status": "complete",
        }
    )

    if _is_outfit_error(outfit):
        session["status"] = "outfit_error"
        session["error"] = (
            outfit.strip()
            if isinstance(outfit, str) and outfit.strip()
            else "I found a listing, but no outfit suggestion was returned."
        )
        return session

    session["outfit_suggestion"] = outfit
    session["status"] = "outfit_created"

    # Step 6: pass the stored outfit and same selected item into Tool 3.
    try:
        fit_card = create_fit_card(
            outfit=session["outfit_suggestion"],
            new_item=session["selected_item"],
        )
    except Exception as exc:
        session["status"] = "fit_card_error"
        session["error"] = (
            "I found the listing and created an outfit, but I couldn't create "
            f"the fit card. Details: {exc}"
        )
        session["tool_trace"].append(
            {
                "tool": "create_fit_card",
                "status": "error",
            }
        )
        return session

    session["tool_trace"].append(
        {
            "tool": "create_fit_card",
            "input_item_id": session["selected_item"].get("id"),
            "status": "complete",
        }
    )

    if _is_fit_card_error(fit_card):
        session["status"] = "fit_card_error"
        session["error"] = (
            fit_card.strip()
            if isinstance(fit_card, str) and fit_card.strip()
            else "The fit-card tool returned no caption."
        )
        return session

    session["fit_card"] = fit_card
    session["status"] = "complete"

    # Step 7: return all accumulated state.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pprint import pprint

    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")

    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )

    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\nSession state:")
    pprint(session)

    print("\n\n=== No-results path ===\n")

    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )

    print(f"Error message: {session2['error']}")
    print(f"Selected item: {session2['selected_item']}")
    print(f"Outfit: {session2['outfit_suggestion']}")
    print(f"Fit card: {session2['fit_card']}")

