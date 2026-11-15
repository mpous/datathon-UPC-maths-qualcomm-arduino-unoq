"""
# Kangaroo Exam Model Evaluation & Solver

Entrypoint and presentation page for the multipage Streamlit application,
introducing the multiclass model evaluation dashboard and the Kangaroo exam
image solver.

- @author: Marc Bosch Manzano
- @date: 14/11/2026
- @ai-usage: Gemini Hydrogen (High)
"""

import pandas as pd
import streamlit as st


def render_feature_card(
    title: str,
    description: str,
    page_path: str,
    link_label: str,
    icon: str,
) -> None:
    """Renders a bordered presentation card with a page navigation link.

    Args:
        title: Heading text for the card.
        description: Summary of the page functionality.
        page_path: Relative path to the target Streamlit page.
        link_label: Text displayed on the navigation button.
        icon: Emoji icon shown alongside the link.
    """
    with st.container(border=True):
        st.subheader(title)
        st.write(description)
        st.page_link(page_path, label=link_label, icon=icon)


def render_schema_overview() -> None:
    """Displays a summary table of the expected evaluation CSV schema."""
    st.subheader("Expected Evaluation Dataset Schema")
    schema_rows: list[dict[str, str]] = [
        {
            "Column": "id",
            "Type": "string",
            "Description": "Unique exercise identifier (e.g., lvl-0_2016_8).",
        },
        {
            "Column": "language / level",
            "Type": "string / int",
            "Description": "Exam language code and difficulty tier.",
        },
        {
            "Column": "has_options",
            "Type": "bool",
            "Description": "Whether multiple-choice options were provided.",
        },
        {
            "Column": "label / answer",
            "Type": "string (A-E)",
            "Description": "Ground-truth letter and model predicted option.",
        },
        {
            "Column": "seconds / status",
            "Type": "float / string",
            "Description": "Inference latency and execution status message.",
        },
        {
            "Column": "prompt_tokens",
            "Type": "int",
            "Description": "Number of input tokens processed by the model.",
        },
    ]
    st.dataframe(
        pd.DataFrame(schema_rows),
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    """Configures and renders the presentation home page."""
    st.set_page_config(
        page_title="Kangaroo Exam AI - Home",
        page_icon="🦘",
        layout="wide",
    )
    st.title("🦘 Kangaroo Math Exam Evaluation & Solver")
    st.markdown(
        "Welcome to the evaluation and inference workspace for multiclass "
        "exam classification models (**A** through **E**)."
    )
    st.divider()

    col_analytics, col_uploader = st.columns(2)
    with col_analytics:
        render_feature_card(
            title="📊 Model Analytics",
            description=(
                "Inspect global KPIs, normalized confusion matrices, class "
                "bias distributions, kernel density plots, segmented "
                "metrics, and execution error logs from CSV evaluations."
            ),
            page_path="pages/analytics.py",
            link_label="Open Analytics Dashboard",
            icon="📊",
        )
    with col_uploader:
        render_feature_card(
            title="🖼️ Exercise Uploader & Solver",
            description=(
                "Upload a Kangaroo exam exercise (.jpg) to extract its "
                "structured dictionary encoding, predicted multiple-choice "
                "answer, and step-by-step reasoning explanation."
            ),
            page_path="pages/uploader.py",
            link_label="Open Image Uploader",
            icon="🖼️",
        )

    st.divider()
    render_schema_overview()


if __name__ == "__main__":
    main()