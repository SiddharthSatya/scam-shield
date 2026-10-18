"""Bank's fraud-team dashboard: live feed of Scam Shield decisions from BigQuery."""

import altair as alt
import pandas as pd
import streamlit as st

from ui import data
from ui.fmt import inr

REFRESH_S = 10
SERIES_1 = "#2a78d6"  # dataviz reference palette, categorical slot 1

# Status is never colour alone: every state carries an icon and a word.
STATUS = {
    "pass": "✅ Passed",
    "ask": "❓ Asked",
    "hold": "⛔ Held",
    "cooling_off": "⏳ Cooling-off",
}
ACTIONS = {
    "cancel_payment": "🛑 Cancelled",
    "continue_anyway": "⚠️ Continued",
    "call_bank": "📞 Called bank",
}
SCAM_NAMES = {
    "digital_arrest": "Digital arrest",
    "kyc_update": "Fake KYC update",
    "job_task": "Job / task",
    "fake_courier": "Fake courier",
    "investment": "Investment",
    "none": "No scam",
}


def page() -> None:
    st.title("🛡️ Scam Shield · Fraud team")
    st.caption(f"Last 24 hours, live from BigQuery. Refreshes every {REFRESH_S} s.")
    _live()


@st.fragment(run_every=REFRESH_S)
def _live() -> None:
    df = data.recent_checks()
    if df.empty:
        st.info("No payments checked yet. Make one in the Demo Bank.")
        return
    df["outcome"] = df.final_decision.fillna(df.money_decision)
    _kpis(df)
    left, right = st.columns([2, 3], gap="large")
    with left:
        _scam_types(df)
    with right:
        _feed(df)


def _kpis(df: pd.DataFrame) -> None:
    held = df[df.outcome.isin(["hold", "cooling_off"])]
    cancelled = df[df.action == "cancel_payment"]
    asked = df[df.money_decision == "ask"]
    a, b, c, d = st.columns(4)
    a.metric("Payments checked", f"{len(df):,}")
    b.metric("Safety checks shown", f"{len(asked):,}",
             help="Money score was high enough to ask the customer 1–3 questions.")
    c.metric("Payments paused", f"{len(held):,}")
    d.metric("Money protected", inr(cancelled.amount_inr.sum()),
             help="Paused payments the customer then cancelled.")


def _scam_types(df: pd.DataFrame) -> None:
    st.markdown("**Paused payments by scam type**")
    held = df[df.outcome.isin(["hold", "cooling_off"])]
    if held.empty:
        st.caption("Nothing paused yet.")
        return
    counts = (held.scam_type.fillna("none").map(SCAM_NAMES).value_counts()
              .rename_axis("scam").reset_index(name="payments"))
    base = alt.Chart(counts).encode(
        y=alt.Y("scam:N", sort="-x", title=None, axis=alt.Axis(labelLimit=160, ticks=False,
                                                              domain=False)),
        x=alt.X("payments:Q", title=None, axis=None),
    )
    bars = base.mark_bar(color=SERIES_1, cornerRadiusEnd=4, height=18).encode(
        tooltip=[alt.Tooltip("scam:N", title="Scam type"),
                 alt.Tooltip("payments:Q", title="Payments paused")])
    labels = base.mark_text(align="left", dx=6).encode(text="payments:Q")
    st.altair_chart((bars + labels).properties(height=40 * len(counts) + 20),
                    width="stretch")


def _feed(df: pd.DataFrame) -> None:
    st.markdown("**Latest payments**")
    feed = pd.DataFrame({
        "Time (IST)": df.ts.dt.tz_convert("Asia/Kolkata").dt.strftime("%H:%M:%S"),
        "Customer": df.customer,
        "Payee": df.payee,
        "Amount": df.amount_inr.map(inr),
        "Money": df.money_score,
        "Decision": df.outcome.map(STATUS),
        "Scam type": df.scam_type.map(SCAM_NAMES).fillna(""),
        "Customer action": df.action.map(ACTIONS).fillna(""),
    }).head(25)
    st.dataframe(
        feed, hide_index=True, width="stretch",
        column_config={"Money": st.column_config.ProgressColumn(
            "Money score", min_value=0.0, max_value=1.0, format="%.2f")},
    )
