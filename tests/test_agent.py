
"""Tests for the FitFindr planning loop and state management."""

import agent


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


def test_parse_complete_query():
    parsed = agent._parse_query(
        "I'm looking for a vintage graphic tee under $30, size M"
    )

    assert parsed == {
        "description": "vintage graphic tee",
        "size": "M",
        "max_price": 30.0,
    }


def test_parse_query_without_size():
    parsed = agent._parse_query(
        "looking for a vintage graphic tee under $30"
    )

    assert parsed["description"] == "vintage graphic tee"
    assert parsed["size"] is None
    assert parsed["max_price"] == 30.0


def test_agent_happy_path_passes_state_between_tools(monkeypatch):
    item = sample_item()
    wardrobe = {
        "items": [
            {
                "id": "w1",
                "name": "Baggy jeans",
                "category": "bottoms",
                "colors": ["blue"],
                "style_tags": ["baggy"],
                "notes": None,
            }
        ]
    }

    expected_outfit = "Wear it with the Baggy jeans."
    expected_card = "Test Graphic Tee with baggy denim for $20 from depop."

    state_checks = {
        "outfit_received_same_item": False,
        "outfit_received_same_wardrobe": False,
        "card_received_same_item": False,
        "card_received_same_outfit": False,
    }

    def fake_search_listings(description, size, max_price):
        assert description == "vintage graphic tee"
        assert size == "M"
        assert max_price == 30.0
        return [item]

    def fake_suggest_outfit(new_item, received_wardrobe):
        state_checks["outfit_received_same_item"] = new_item is item
        state_checks["outfit_received_same_wardrobe"] = (
            received_wardrobe is wardrobe
        )
        return expected_outfit

    def fake_create_fit_card(outfit, new_item):
        state_checks["card_received_same_item"] = new_item is item
        state_checks["card_received_same_outfit"] = (
            outfit == expected_outfit
        )
        return expected_card

    monkeypatch.setattr(
        agent,
        "search_listings",
        fake_search_listings,
    )
    monkeypatch.setattr(
        agent,
        "suggest_outfit",
        fake_suggest_outfit,
    )
    monkeypatch.setattr(
        agent,
        "create_fit_card",
        fake_create_fit_card,
    )

    session = agent.run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=wardrobe,
    )

    assert session["error"] is None
    assert session["status"] == "complete"
    assert session["search_results"] == [item]
    assert session["selected_item"] is item
    assert session["outfit_suggestion"] == expected_outfit
    assert session["fit_card"] == expected_card

    assert all(state_checks.values())


def test_agent_no_results_stops_before_other_tools(monkeypatch):
    calls = {
        "search": 0,
        "outfit": 0,
        "card": 0,
    }

    def fake_search_listings(description, size, max_price):
        calls["search"] += 1
        return []

    def forbidden_outfit(*args, **kwargs):
        calls["outfit"] += 1
        raise AssertionError(
            "suggest_outfit must not run after an empty search."
        )

    def forbidden_card(*args, **kwargs):
        calls["card"] += 1
        raise AssertionError(
            "create_fit_card must not run after an empty search."
        )

    monkeypatch.setattr(
        agent,
        "search_listings",
        fake_search_listings,
    )
    monkeypatch.setattr(
        agent,
        "suggest_outfit",
        forbidden_outfit,
    )
    monkeypatch.setattr(
        agent,
        "create_fit_card",
        forbidden_card,
    )

    session = agent.run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe={"items": []},
    )

    assert calls == {
        "search": 1,
        "outfit": 0,
        "card": 0,
    }

    assert session["status"] == "no_results"
    assert session["error"] is not None
    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_agent_stops_when_outfit_fails(monkeypatch):
    item = sample_item()
    card_called = False

    monkeypatch.setattr(
        agent,
        "search_listings",
        lambda **kwargs: [item],
    )

    monkeypatch.setattr(
        agent,
        "suggest_outfit",
        lambda **kwargs: (
            "I couldn't create an outfit because the item is incomplete."
        ),
    )

    def forbidden_card(*args, **kwargs):
        nonlocal card_called
        card_called = True
        raise AssertionError(
            "create_fit_card must not run after an outfit failure."
        )

    monkeypatch.setattr(
        agent,
        "create_fit_card",
        forbidden_card,
    )

    session = agent.run_agent(
        query="graphic tee under $30",
        wardrobe={"items": []},
    )

    assert session["status"] == "outfit_error"
    assert session["error"] is not None
    assert session["fit_card"] is None
    assert card_called is False


def test_agent_empty_query_returns_early(monkeypatch):
    def forbidden_search(*args, **kwargs):
        raise AssertionError(
            "Search must not run for an empty query."
        )

    monkeypatch.setattr(
        agent,
        "search_listings",
        forbidden_search,
    )

    session = agent.run_agent(
        query="   ",
        wardrobe={"items": []},
    )

    assert session["status"] == "invalid_query"
    assert session["error"] is not None
    assert session["fit_card"] is None