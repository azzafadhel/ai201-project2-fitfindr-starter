"""Tests for the three FitFindr tools."""

import tools

from tools import (
    create_fit_card,
    search_listings,
    suggest_outfit,
)

from utils.data_loader import (
    get_empty_wardrobe,
    get_example_wardrobe,
)


def sample_listing() -> dict:
    """Return a complete listing for isolated tool tests."""
    return {
        "id": "lst_002",
        "title": "Y2K Baby Tee — Butterfly Print",
        "description": "Early 2000s baby tee with a butterfly graphic.",
        "category": "tops",
        "style_tags": [
            "y2k",
            "vintage",
            "graphic tee",
            "cottagecore",
        ],
        "size": "S/M",
        "condition": "excellent",
        "price": 18.00,
        "colors": ["white", "pink", "purple"],
        "brand": None,
        "platform": "depop",
    }


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings(
        description="vintage graphic tee",
        size=None,
        max_price=50,
    )

    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings(
        description="designer ballgown",
        size="XXS",
        max_price=5,
    )

    assert results == []


def test_search_price_filter():
    results = search_listings(
        description="vintage",
        size=None,
        max_price=20,
    )

    assert len(results) > 0
    assert all(item["price"] <= 20 for item in results)


def test_search_combined_size_matches_medium():
    results = search_listings(
        description="vintage graphic tee",
        size="M",
        max_price=30,
    )

    assert len(results) > 0
    assert results[0]["id"] == "lst_002"
    assert results[0]["size"] == "S/M"


def test_search_blank_description():
    results = search_listings(
        description="",
        size=None,
        max_price=50,
    )

    assert results == []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe(monkeypatch):
    fake_response = (
        "Pair the Y2K Baby Tee with your Baggy straight-leg jeans, "
        "dark wash and Chunky white sneakers for a relaxed Y2K look."
    )

    monkeypatch.setattr(
        tools,
        "_call_llm",
        lambda *args, **kwargs: fake_response,
    )

    result = suggest_outfit(
        new_item=sample_listing(),
        wardrobe=get_example_wardrobe(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "Baggy straight-leg jeans" in result
    assert "Chunky white sneakers" in result


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    fake_response = (
        "Style it with relaxed jeans and neutral sneakers for an easy "
        "Y2K outfit. Add a small front tuck for shape."
    )

    monkeypatch.setattr(
        tools,
        "_call_llm",
        lambda *args, **kwargs: fake_response,
    )

    result = suggest_outfit(
        new_item=sample_listing(),
        wardrobe=get_empty_wardrobe(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "wardrobe is empty" in result.lower()
    assert "general recommendations" in result.lower()


def test_suggest_outfit_missing_item():
    result = suggest_outfit(
        new_item={},
        wardrobe=get_example_wardrobe(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "couldn't create an outfit" in result.lower()


def test_suggest_outfit_llm_failure_uses_fallback(monkeypatch):
    def fake_failure(*args, **kwargs):
        raise RuntimeError("Simulated Groq failure")

    monkeypatch.setattr(
        tools,
        "_call_llm",
        fake_failure,
    )

    result = suggest_outfit(
        new_item=sample_listing(),
        wardrobe=get_example_wardrobe(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "Y2K Baby Tee" in result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_returns_caption(monkeypatch):
    fake_caption = (
        "The Y2K Baby Tee — Butterfly Print brings playful early-2000s "
        "energy with baggy denim and chunky sneakers. This $18 depop "
        "find makes an easy streetwear look 🦋"
    )

    monkeypatch.setattr(
        tools,
        "_call_llm",
        lambda *args, **kwargs: fake_caption,
    )

    outfit = (
        "Pair the tee with baggy dark-wash jeans and chunky white "
        "sneakers for a relaxed Y2K streetwear outfit."
    )

    result = create_fit_card(
        outfit=outfit,
        new_item=sample_listing(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "Y2K Baby Tee" in result
    assert "$18" in result
    assert "depop" in result.lower()


def test_create_fit_card_empty_outfit():
    result = create_fit_card(
        outfit="",
        new_item=sample_listing(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "outfit suggestion is missing" in result.lower()


def test_create_fit_card_missing_listing():
    result = create_fit_card(
        outfit="Pair it with jeans and sneakers.",
        new_item={},
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "listing information is missing" in result.lower()


def test_create_fit_card_llm_failure_uses_fallback(monkeypatch):
    def fake_failure(*args, **kwargs):
        raise RuntimeError("Simulated Groq failure")

    monkeypatch.setattr(
        tools,
        "_call_llm",
        fake_failure,
    )

    outfit = (
        "Pair the tee with baggy dark-wash jeans and chunky white "
        "sneakers for a relaxed Y2K streetwear outfit."
    )

    result = create_fit_card(
        outfit=outfit,
        new_item=sample_listing(),
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "Y2K Baby Tee" in result
    assert "$18.00" in result
    assert "depop" in result.lower()
