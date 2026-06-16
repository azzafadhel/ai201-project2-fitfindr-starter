"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up.
handle_query() calls run_agent() and maps session data to the output panels.

Run with:
    python app.py
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── output formatting ─────────────────────────────────────────────────────────

def _format_listing(item: dict, result_count: int) -> str:
    """Format the selected listing for the first Gradio output panel."""
    price = item.get("price")

    if isinstance(price, (int, float)):
        price_text = f"${price:.2f}"
    else:
        price_text = "Not provided"

    colors = item.get("colors", [])
    style_tags = item.get("style_tags", [])

    if isinstance(colors, list):
        colors_text = ", ".join(str(color) for color in colors)
    else:
        colors_text = str(colors)

    if isinstance(style_tags, list):
        tags_text = ", ".join(str(tag) for tag in style_tags)
    else:
        tags_text = str(style_tags)

    brand = item.get("brand") or "Unbranded"

    return "\n".join(
        [
            f"Top match out of {result_count} result(s)",
            "",
            f"Title: {item.get('title', 'Unknown item')}",
            f"Price: {price_text}",
            f"Size: {item.get('size', 'Not provided')}",
            f"Condition: {item.get('condition', 'Not provided')}",
            f"Brand: {brand}",
            f"Platform: {item.get('platform', 'Not provided')}",
            f"Colors: {colors_text or 'Not provided'}",
            f"Style tags: {tags_text or 'Not provided'}",
            "",
            f"Description: {item.get('description', 'Not provided')}",
        ]
    )


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Call the FitFindr agent and map session results to three UI panels.
    """
    # Step 1: reject an empty query before calling the agent.
    if not isinstance(user_query, str) or not user_query.strip():
        return (
            "Please enter an item description, such as "
            "'vintage graphic tee under $30, size M.'",
            "",
            "",
        )

    # Step 2: select the requested wardrobe.
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # Step 3: run the agent.
    try:
        session = run_agent(
            query=user_query.strip(),
            wardrobe=wardrobe,
        )
    except Exception as exc:
        return (
            f"FitFindr could not complete the request: {exc}",
            "",
            "",
        )

    # Step 4: show an early-termination error in the first panel.
    if session.get("error"):
        return (
            session["error"],
            "",
            "",
        )

    # Step 5: map successful session state into the output panels.
    selected_item = session.get("selected_item")

    if not isinstance(selected_item, dict) or not selected_item:
        return (
            "The agent completed the search but did not return a valid listing.",
            "",
            "",
        )

    listing_text = _format_listing(
        selected_item,
        result_count=len(session.get("search_results", [])),
    )

    outfit_text = session.get("outfit_suggestion") or (
        "No outfit suggestion was generated."
    )

    fit_card_text = session.get("fit_card") or (
        "No fit card was generated."
    )

    return (
        listing_text,
        outfit_text,
        fit_card_text,
    )


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",
]


def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=[
                    "Example wardrobe",
                    "Empty wardrobe (new user)",
                ],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[
                [query, "Example wardrobe"]
                for query in EXAMPLE_QUERIES
            ],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[
                listing_output,
                outfit_output,
                fitcard_output,
            ],
        )

        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[
                listing_output,
                outfit_output,
                fitcard_output,
            ],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()

