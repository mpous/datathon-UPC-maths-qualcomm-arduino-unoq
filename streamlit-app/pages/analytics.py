"""
# Model Evaluation Analytics

Interactive Streamlit page dedicated to evaluating multiclass exam response
models (A through E) across confusion matrices, class bias charts, kernel
density plots, segmented metrics, and execution error logs.

- @author: Marc Bosch Manzano
- @date: 14/11/2026
- @ai-usage: Gemini Hydrogen (High)
"""

import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go
import streamlit as st
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
)

CLASSES: list[str] = ["A", "B", "C", "D", "E"]

SAMPLE_CSV: str = (
    "id,language,level,has_options,label,answer,correct,seconds,status,"
    "prompt_tokens,retrieved\n"
    "lvl-0_2016_8,eng,0,False,C,D,0,2.12,error: [WinError 10061],0,\n"
    "lvl-0_2015_17,eng,0,True,D,D,1,2.03,error: [WinError 10061],0,\n"
    "lvl-0_2016_20,eng,0,True,C,D,0,2.04,error: [WinError 10061],0,\n"
    "lvl-0_2017_19,eng,0,False,A,D,0,2.05,error: [WinError 10061],0,\n"
    "lvl-0_2015_14,eng,0,True,C,D,0,2.03,error: [WinError 10061],0,\n"
    "lvl-0_2017_2,eng,0,True,B,D,0,2.04,error: [WinError 10061],0,\n"
)


@st.cache_data
def load_csv(file_bytes: bytes | None) -> pd.DataFrame:
    """Loads and normalizes the evaluation CSV dataset.

    Args:
        file_bytes: Raw bytes from an uploaded CSV file, or None for sample.

    Returns:
        Normalized DataFrame ready for evaluation.
    """
    if file_bytes is None:
        df = pd.read_csv(io.StringIO(SAMPLE_CSV))
    else:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")

    for col in ["label", "answer"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    if "status" in df.columns:
        df["status"] = df["status"].fillna("ok").astype(str)
        df["has_exec_error"] = (
            df["status"].str.lower().str.contains("error")
        )
    else:
        df["has_exec_error"] = False

    if "correct" not in df.columns and {"label", "answer"}.issubset(
        df.columns
    ):
        df["correct"] = (df["label"] == df["answer"]).astype(int)

    return df


def apply_categorical_filter(
    df: pd.DataFrame, col: str, label: str
) -> pd.DataFrame:
    """Applies a sidebar multiselect filter if the column exists.

    Args:
        df: Input DataFrame to filter.
        col: Column name to filter on.
        label: Display label for the Streamlit widget.

    Returns:
        Filtered DataFrame containing only selected values.
    """
    if col not in df.columns:
        return df
    options = sorted(df[col].dropna().unique().tolist())
    selected = st.multiselect(label, options, default=options)
    return df[df[col].isin(selected)]


def filter_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Renders sidebar filters and returns the filtered dataset.

    Args:
        df_raw: Unfiltered DataFrame.

    Returns:
        Filtered DataFrame based on user selections.
    """
    st.header("2. Filters")
    exclude_errors = st.checkbox(
        "Exclude rows with execution error (status = error)",
        value=False,
        help="Filter out rows where the API or server failed.",
    )
    df = (
        df_raw[~df_raw["has_exec_error"]].copy()
        if exclude_errors
        else df_raw.copy()
    )
    filter_specs = [
        ("language", "Language (language)"),
        ("level", "Level (level)"),
        ("has_options", "Has options (has_options)"),
    ]
    for col, label in filter_specs:
        df = apply_categorical_filter(df, col, label)
    return df


def compute_metrics(
    y_true: pd.Series, y_pred: pd.Series
) -> dict[str, float]:
    """Computes multiclass evaluation metrics for classes A through E.

    Args:
        y_true: Series of ground-truth class labels.
        y_pred: Series of predicted class labels.

    Returns:
        Dictionary mapping metric names to their computed float values.
    """
    f1_macro = f1_score(
        y_true, y_pred, labels=CLASSES, average="macro", zero_division=0
    )
    f1_weighted = f1_score(
        y_true, y_pred, labels=CLASSES, average="weighted", zero_division=0
    )
    return {
        "Accuracy": float(accuracy_score(y_true, y_pred)),
        "Balanced Accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "F1 (Macro)": float(f1_macro),
        "F1 (Weighted)": float(f1_weighted),
        "Cohen's Kappa": float(
            cohen_kappa_score(y_true, y_pred, labels=CLASSES)
        ),
        "Matthews (MCC)": float(matthews_corrcoef(y_true, y_pred)),
    }


def render_metric_row(
    items: list[tuple[str, str, str | None, str]],
) -> None:
    """Renders a horizontal row of Streamlit metric cards.

    Args:
        items: Tuples of (label, value, delta, help_text) for each metric.
    """
    cols = st.columns(len(items))
    for col, (label, value, delta, help_text) in zip(cols, items):
        is_negative = delta is not None and delta.startswith("-")
        col.metric(
            label=label,
            value=value,
            delta=delta,
            delta_color="inverse" if is_negative else "off",
            help=help_text,
        )


def render_kpis(df: pd.DataFrame, df_valid: pd.DataFrame) -> None:
    """Displays execution summary and global classification metrics.

    Args:
        df: Filtered DataFrame including all status rows.
        df_valid: Subset of df with valid predictions in A-E.
    """
    st.subheader("Execution Summary and Global Metrics")
    invalid_count = len(df) - len(df_valid)
    delta_valid = (
        f"-{invalid_count} invalid" if invalid_count else "100% valid"
    )
    exec_items: list[tuple[str, str, str | None, str]] = [
        ("Evaluated samples", f"{len(df):,}", None, "Total rows."),
        (
            "Valid answers (A-E)",
            f"{len(df_valid):,}",
            delta_valid,
            "Rows with label and answer in A-E.",
        ),
    ]
    if "seconds" in df.columns:
        lat_val = f"{df['seconds'].mean():.2f} s"
        lat_delta = f"Median: {df['seconds'].median():.2f} s"
        exec_items.append(
            ("Mean latency", lat_val, lat_delta, "Time per sample.")
        )
    if "prompt_tokens" in df.columns:
        tok_val = f"{df['prompt_tokens'].mean():.0f}"
        exec_items.append(
            ("Mean tokens", tok_val, None, "Average prompt_tokens.")
        )
    render_metric_row(exec_items)

    if df_valid.empty:
        return

    scores = compute_metrics(df_valid["label"], df_valid["answer"])
    score_items: list[tuple[str, str, str | None, str]] = [
        ("Accuracy", f"{scores['Accuracy']:.2%}", None, "Total hits."),
        (
            "Balanced Accuracy",
            f"{scores['Balanced Accuracy']:.2%}",
            None,
            "Average recall across classes.",
        ),
        (
            "F1 (Macro)",
            f"{scores['F1 (Macro)']:.3f}",
            None,
            "Unweighted mean F1 score.",
        ),
        (
            "F1 (Weighted)",
            f"{scores['F1 (Weighted)']:.3f}",
            None,
            "F1 weighted by class support.",
        ),
        (
            "Cohen's Kappa",
            f"{scores['Cohen\'s Kappa']:.3f}",
            None,
            "Chance-corrected agreement.",
        ),
        (
            "Matthews (MCC)",
            f"{scores['Matthews (MCC)']:.3f}",
            None,
            "Multiclass correlation (-1 to +1).",
        ),
    ]
    render_metric_row(score_items)


def build_confusion_matrix(
    y_true: pd.Series, y_pred: pd.Series, normalize: bool
) -> go.Figure:
    """Creates an interactive Plotly confusion matrix figure.

    Args:
        y_true: Ground-truth labels.
        y_pred: Model predicted labels.
        normalize: Whether to normalize rows by true class support (%).

    Returns:
        Configured Plotly Figure object.
    """
    cm = confusion_matrix(y_true, y_pred, labels=CLASSES)
    if normalize:
        row_sums = cm.sum(axis=1, keepdims=True)
        cm_display = (
            np.divide(
                cm,
                row_sums,
                out=np.zeros_like(cm, dtype=float),
                where=row_sums != 0,
            )
            * 100
        )
        text_fmt = ".1f"
        title = "Normalized Confusion Matrix (%)"
    else:
        cm_display = cm
        text_fmt = "d"
        title = "Confusion Matrix (Counts)"

    fig = px.imshow(
        cm_display,
        x=CLASSES,
        y=CLASSES,
        labels={
            "x": "Prediction (answer)",
            "y": "Ground truth (label)",
            "color": "Value",
        },
        color_continuous_scale="Blues",
        aspect="equal",
    )
    fig.update_traces(
        text=cm_display, texttemplate=f"%{{text:{text_fmt}}}"
    )
    fig.update_layout(title=title, height=460)
    return fig


def build_bias_chart(y_true: pd.Series, y_pred: pd.Series) -> go.Figure:
    """Creates a grouped bar chart comparing true vs predicted counts.

    Args:
        y_true: Ground-truth labels.
        y_pred: Model predicted labels.

    Returns:
        Configured Plotly Figure object.
    """
    dist_df = pd.DataFrame(
        {
            "Class": CLASSES,
            "Actual (label)": [int((y_true == c).sum()) for c in CLASSES],
            "Predicted (answer)": [
                int((y_pred == c).sum()) for c in CLASSES
            ],
        }
    ).melt(id_vars="Class", var_name="Type", value_name="Count")

    fig = px.bar(
        dist_df,
        x="Class",
        y="Count",
        color="Type",
        barmode="group",
        color_discrete_map={
            "Actual (label)": "steelblue",
            "Predicted (answer)": "coral",
        },
    )
    fig.update_layout(title="Actual vs. Predicted Distribution", height=420)
    return fig


def render_classification_tab(df_valid: pd.DataFrame) -> None:
    """Renders the confusion matrix, bias chart, and per-class metrics.

    Args:
        df_valid: DataFrame containing valid A-E labels and predictions.
    """
    if df_valid.empty:
        st.warning("No predictions found within classes A-E.")
        return

    y_true = df_valid["label"]
    y_pred = df_valid["answer"]
    col_cm, col_dist = st.columns([1.2, 1.0])

    with col_cm:
        mode = st.radio(
            "Display mode:",
            ["Absolute counts", "Normalized by true class (%)"],
            horizontal=True,
        )
        fig_cm = build_confusion_matrix(
            y_true, y_pred, normalize=mode.startswith("Normalized")
        )
        st.plotly_chart(fig_cm, use_container_width=True)

    with col_dist:
        fig_bias = build_bias_chart(y_true, y_pred)
        st.plotly_chart(fig_bias, use_container_width=True)

    st.markdown("### Detailed Per-Class Report")
    report_dict = classification_report(
        y_true, y_pred, labels=CLASSES, output_dict=True, zero_division=0
    )
    report_df = pd.DataFrame(report_dict).transpose().loc[CLASSES]
    report_df["support"] = report_df["support"].astype(int)
    styled_df = report_df.style.format(
        {"precision": "{:.3f}", "recall": "{:.3f}", "f1-score": "{:.3f}"}
    ).background_gradient(
        cmap="YlGnBu", subset=["precision", "recall", "f1-score"]
    )
    st.dataframe(styled_df, use_container_width=True)


def prepare_density_data(
    df: pd.DataFrame, target_var: str, group_var: str
) -> pd.DataFrame:
    """Prepares clean data with human-readable group labels for plotting.

    Args:
        df: Filtered DataFrame.
        target_var: Numeric column name for the X axis.
        group_var: Categorical column name for grouping.

    Returns:
        Cleaned two-column DataFrame with formatted group strings.
    """
    plot_df = df[[target_var, group_var]].dropna().copy()
    if group_var == "correct":
        mapped = plot_df[group_var].map({1: "1 - Correct", 0: "0 - Incorrect"})
        plot_df[group_var] = mapped.fillna(plot_df[group_var].astype(str))
    else:
        plot_df[group_var] = plot_df[group_var].astype(str)
    return plot_df


def build_density_figure(
    plot_df: pd.DataFrame, target_var: str, group_var: str
) -> tuple[go.Figure, bool]:
    """Builds a KDE density plot or falls back to a box-marginal histogram.

    Args:
        plot_df: Prepared DataFrame with target and group columns.
        target_var: Numeric variable name.
        group_var: Grouping variable name.

    Returns:
        Tuple of (Plotly Figure, True if KDE was computed else False).
    """
    hist_data: list[np.ndarray] = []
    group_labels: list[str] = []

    for grp in sorted(plot_df[group_var].unique()):
        vals = plot_df[plot_df[group_var] == grp][target_var].to_numpy()
        if len(vals) >= 2 and np.std(vals) > 1e-6:
            hist_data.append(vals)
            group_labels.append(f"{grp} (n={len(vals)})")

    if hist_data:
        span = float(plot_df[target_var].max() - plot_df[target_var].min())
        bin_size = span / 25.0 if span > 0 else 0.1
        fig = ff.create_distplot(
            hist_data,
            group_labels,
            show_hist=True,
            show_rug=True,
            bin_size=bin_size,
        )
        fig.update_layout(
            title=f"Density Plot (KDE) of '{target_var}' by '{group_var}'",
            xaxis_title=target_var,
            yaxis_title="Density",
            height=460,
        )
        return fig, True

    fig_hist = px.histogram(
        plot_df,
        x=target_var,
        color=group_var,
        marginal="box",
        barmode="overlay",
        title=f"Distribution of '{target_var}' by '{group_var}'",
    )
    return fig_hist, False


def render_density_tab(df: pd.DataFrame) -> None:
    """Renders KDE density plots and violin plots for numeric columns.

    Args:
        df: Filtered DataFrame.
    """
    num_cols = [c for c in ["seconds", "prompt_tokens"] if c in df.columns]
    grp_cols = [
        c
        for c in ["correct", "level", "language", "label"]
        if c in df.columns
    ]
    if not num_cols or not grp_cols:
        st.info("Missing numeric or grouping columns in the CSV.")
        return

    col_x, col_g = st.columns(2)
    with col_x:
        target_var = st.selectbox("Numeric variable (X axis):", num_cols)
    with col_g:
        group_var = st.selectbox("Group density by:", grp_cols)

    plot_df = prepare_density_data(df, target_var, group_var)
    fig_density, is_kde = build_density_figure(
        plot_df, target_var, group_var
    )
    if not is_kde:
        st.info(
            "Insufficient variance to compute a KDE curve. "
            "Showing an alternative histogram."
        )
    st.plotly_chart(fig_density, use_container_width=True)

    fig_violin = px.violin(
        plot_df,
        x=group_var,
        y=target_var,
        color=group_var,
        box=True,
        points="all",
        title=f"Violin Plot of '{target_var}' by '{group_var}'",
    )
    st.plotly_chart(fig_violin, use_container_width=True)


def compute_segment_stats(
    df_valid: pd.DataFrame, seg_col: str
) -> pd.DataFrame:
    """Aggregates accuracy, macro F1, and latency across a segment column.

    Args:
        df_valid: DataFrame with valid A-E labels and answers.
        seg_col: Column name used to group samples.

    Returns:
        Summary DataFrame with one row per segment value.
    """
    rows: list[dict[str, object]] = []
    for val, sub in df_valid.groupby(seg_col):
        lat = sub["seconds"].mean() if "seconds" in sub.columns else np.nan
        f1_val = f1_score(
            sub["label"],
            sub["answer"],
            labels=CLASSES,
            average="macro",
            zero_division=0,
        )
        rows.append(
            {
                seg_col: str(val),
                "Samples": len(sub),
                "Accuracy": float(
                    accuracy_score(sub["label"], sub["answer"])
                ),
                "Macro F1": float(f1_val),
                "Mean latency (s)": float(lat),
            }
        )
    return pd.DataFrame(rows)


def render_segments_tab(df_valid: pd.DataFrame) -> None:
    """Renders segmented performance charts and summary tables.

    Args:
        df_valid: DataFrame with valid A-E labels and answers.
    """
    seg_cols = [
        c
        for c in ["level", "language", "has_options"]
        if c in df_valid.columns
    ]
    if not seg_cols or df_valid.empty:
        st.info("No segmentation columns available.")
        return

    seg_choice = st.selectbox("Analyze performance by:", seg_cols)
    seg_df = compute_segment_stats(df_valid, seg_choice)
    melted = seg_df.melt(
        id_vars=[seg_choice, "Samples"],
        value_vars=["Accuracy", "Macro F1"],
    )
    fig_seg = px.bar(
        melted,
        x=seg_choice,
        y="value",
        color="variable",
        barmode="group",
        text_auto=".2%",
        title=f"Accuracy and Macro F1 by '{seg_choice}'",
    )
    fig_seg.update_yaxes(range=[0, 1.05])
    st.plotly_chart(fig_seg, use_container_width=True)
    st.dataframe(seg_df, use_container_width=True)


def render_errors_tab(df: pd.DataFrame) -> None:
    """Renders execution status breakdown and failed prediction samples.

    Args:
        df: Filtered DataFrame.
    """
    if "status" in df.columns:
        st.markdown("### Execution Status Summary (`status`)")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status", "Count"]
        st.dataframe(status_counts, use_container_width=True)

    st.markdown("### Failed Samples (`correct == 0`)")
    if "correct" in df.columns:
        wrong_df = df[df["correct"] == 0]
    else:
        wrong_df = df[df["label"] != df["answer"]]
    st.write(f"Total errors: **{len(wrong_df)}**")
    st.dataframe(wrong_df, use_container_width=True)


def main() -> None:
    """Configures and runs the model evaluation analytics page."""
    st.set_page_config(
        page_title="Model Evaluation Analytics",
        page_icon="📊",
        layout="wide",
    )
    st.title("📊 Model Evaluation Analytics (A-E Responses)")

    with st.sidebar:
        st.header("1. Data")
        uploaded = st.file_uploader("Upload evaluation CSV", type=["csv"])
        if uploaded is None:
            st.info("Showing sample data. Upload a complete CSV.")
        df_raw = load_csv(uploaded.getvalue() if uploaded else None)
        df = filter_dataframe(df_raw)

    if df.empty:
        st.error("No data matches the selected filters.")
        st.stop()

    n_errors = int(df["has_exec_error"].sum())
    if n_errors > 0:
        pct = n_errors / len(df)
        st.warning(
            f"Found {n_errors} of {len(df)} rows ({pct:.1%}) with "
            "execution errors in `status`."
        )

    valid_mask = df["label"].isin(CLASSES) & df["answer"].isin(CLASSES)
    df_valid = df[valid_mask].copy()

    render_kpis(df, df_valid)
    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Confusion Matrix & Classes",
            "Density Plots",
            "Segmented Performance",
            "Error Inspection",
        ]
    )
    with tab1:
        render_classification_tab(df_valid)
    with tab2:
        render_density_tab(df)
    with tab3:
        render_segments_tab(df_valid)
    with tab4:
        render_errors_tab(df)


if __name__ == "__main__":
    main()