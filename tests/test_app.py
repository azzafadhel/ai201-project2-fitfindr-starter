"""Tests for mapping agent state into the Gradio output panels."""

import app


def sample_item() -> dict:
    return {
        "id": "lst_test",
        "title": "Test Graphic Tee",
        "description": "A faded graphic tee.",
        "category": "tops",
        "style_tags": ["vintage", "graphic tee"],
        "size": "M",
        "condition": "good",
        "price": 20.0,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }


def test_handle_query_empty_input():
    listing, outfit, card = app.handle_query(
        "",
        "Example wardrobe",
    )

    assert "please enter" in listing.lower()
    assert outfit == ""
    assert card == ""


def test_handle_query_maps_successful_session(monkeypatch):
    item = sample_item()

    fake_session = {
        "search_results": [item],
        "selected_item": item,
        "outfit_suggestion": "Wear it with baggy jeans.",
        "fit_card": "A relaxed thrifted look.",
        "error": None,
    }

    monkeypatch.setattr(
        app,
        "run_agent",
        lambda query, wardrobe: fake_session,
    )

    listing, outfit, card = app.handle_query(
        "graphic tee under $30",
        "Example wardrobe",
    )

    assert "Test Graphic Tee" in listing
    assert "$20.00" in listing
    assert "depop" in listing
    assert outfit == "Wear it with baggy jeans."
    assert card == "A relaxed thrifted look."


def test_handle_query_maps_error_session(monkeypatch):
    fake_session = {
        "search_results": [],
        "selected_item": None,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": "No listings matched the request.",
    }

    monkeypatch.setattr(
        app,
        "run_agent",
        lambda query, wardrobe: fake_session,
    )

    listing, outfit, card = app.handle_query(
        "designer ballgown under $5",
        "Example wardrobe",
    )

    assert listing == "No listings matched the request."
    assert outfit == ""
    assert card == ""

