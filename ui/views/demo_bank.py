"""'Demo Bank' app: a pretend banking app that calls Scam Shield before every payment."""

import contextlib
import time
from typing import Any

import streamlit as st

from ui import data, render
from ui.api_client import ApiError, ScamShieldClient
from ui.config import get_ui_settings
from ui.fmt import hour_label, inr

S = st.session_state
ACTION_MESSAGES = {
    "cancel_payment": ("success", "Payment cancelled. {amount} stays safely in your account."),
    "call_bank": ("info", "Connecting you to the bank's fraud helpline (demo). "
                          "The payment stays on hold until you speak to us."),
    "continue_anyway": ("warning", "Payment of {amount} sent at your request. "
                                   "If you think this was a scam, call 1930 right away."),
}


@st.cache_resource
def client() -> ScamShieldClient:
    return ScamShieldClient(get_ui_settings())


def reset_flow() -> None:
    for k in ("stage", "check", "final", "message", "timings"):
        S.pop(k, None)
    S["flow_id"] = S.get("flow_id", 0) + 1  # fresh widget keys for the next payment


def load_scenario() -> None:
    scenarios = data.scenarios()
    match = scenarios[scenarios.title == S.get("scenario")]
    if match.empty:
        return
    row = match.iloc[0]
    S["customer_id"] = row.customer_id
    S["payee_id"] = row.payee_id
    S["amount"] = float(row.amount_inr)
    S["hour"] = int(row.hour_ist)
    reset_flow()


def on_customer_change() -> None:
    S.pop("payee_id", None)
    reset_flow()


def pay(customer_id: str, payee_id: str, amount: float, hour: int) -> None:
    start = time.perf_counter()
    try:
        check = client().check_payment(customer_id, payee_id, amount, hour)
    except ApiError as e:
        st.error(str(e))
        return
    S["timings"] = {"money_s": time.perf_counter() - start}
    S["check"] = check
    # Copies: Streamlit drops widget-bound keys (amount, hour) once the form is not shown.
    S["amount_paid"], S["hour_paid"] = amount, hour
    if check["decision"] == "pass":
        S["stage"], S["message"] = "done", ("success", f"Payment of {inr(amount)} sent.")
    elif check["decision"] == "ask":
        S["stage"] = "ask"
    else:
        S["stage"] = "alert"


def send_context(answers: render.Answers) -> None:
    payload: dict[str, Any] = {
        "token": S["check"]["token"],
        **{k: v for k, v in answers.values.items() if k in
           ("purpose", "on_call", "told_to_keep_secret")},
        "message_text": answers.message_text,
        "image_base64": answers.image_base64,
        "image_mime_type": answers.image_mime_type,
    }
    start = time.perf_counter()
    try:
        final = client().submit_context(payload)
    except ApiError as e:
        st.error(str(e))
        return
    S["timings"]["context_s"] = time.perf_counter() - start
    S["final"] = final
    if final["decision"] == "pass":
        S["stage"] = "done"
        S["message"] = ("success", f"Thanks. Payment of {inr(S['amount_paid'])} sent.")
    else:
        S["stage"] = "alert"


def choose(action: str) -> None:
    token = S["check"].get("token")
    if token:
        # If this fails the dashboard misses one outcome; the customer flow must not break.
        with contextlib.suppress(ApiError):
            client().record_outcome(token, action)
    kind, text = ACTION_MESSAGES[action]
    S["stage"], S["message"] = "done", (kind, text.format(amount=inr(S["amount_paid"])))


# ---------- Page ----------

def page() -> None:
    st.title("🏦 Demo Bank")
    st.caption("A pretend banking app. Before every payment, it asks Scam Shield. "
               "In real life, any bank adds this with one API call and one screen.")

    customers = data.demo_customers()
    scenario_titles = data.scenarios().title.tolist()
    st.selectbox("Quick demo: load a scenario", scenario_titles, index=None,
                 key="scenario", on_change=load_scenario, placeholder="Pick a scenario...")

    phone, backstage = st.columns([3, 2], gap="large")
    with phone, st.container(border=True):
        customer = _customer_picker(customers)
        stage = S.get("stage", "form")
        if stage == "form":
            _payment_form(customer)
        elif stage == "ask":
            _summary_line()
            answers = render.safety_check(S["check"]["screen"], key=f"ask-{S.get('flow_id', 0)}")
            if answers:
                with st.spinner("Checking..."):
                    send_context(answers)
                st.rerun()
        elif stage == "alert":
            _summary_line()
            screen = (S.get("final") or {}).get("screen") or S["check"]["screen"]
            action = render.alert(screen, key=f"alert-{S.get('flow_id', 0)}")
            if action:
                choose(action)
                st.rerun()
        else:
            kind, text = S["message"]
            getattr(st, kind)(text)
            st.button("Make another payment", on_click=reset_flow, width="stretch")

    with backstage:
        _behind_the_scenes()


def _customer_picker(customers):
    names = dict(zip(customers.customer_id, customers.display_name, strict=True))
    if S.get("customer_id") not in names:
        S["customer_id"] = customers.customer_id.iloc[0]
    st.selectbox("Logged in as", list(names), format_func=names.get, key="customer_id",
                 on_change=on_customer_change)
    row = customers.set_index("customer_id").loc[S["customer_id"]]
    st.caption(f"{row.city} · age {row.age} · balance **{inr(row.balance_inr)}**")
    return row


def _payment_form(customer) -> None:
    payees = data.payees_for(customer.name)
    labels = {p.payee_id: f"{'🆕 ' if p.is_new else ''}{p.display_name}"
              for p in payees.itertuples()}
    if S.get("payee_id") not in labels:
        S["payee_id"] = payees.payee_id.iloc[0]
    st.selectbox("Pay to", list(labels), format_func=labels.get, key="payee_id")
    balance = float(customer.balance_inr)
    # A bank app never lets you send more than you have. Clamp first: a scenario or a
    # previous customer may have left a bigger amount in state.
    S["amount"] = min(S.get("amount", 1_000.0), balance)
    S.setdefault("hour", 11)
    st.number_input(f"Amount (₹) · available {inr(balance)}", min_value=1.0, max_value=balance,
                    step=500.0, key="amount", format="%.0f")
    st.slider("Time of payment (IST, for the demo)", 0, 23, key="hour",
              format="%d:00")
    if st.button(f"Pay {inr(S['amount'])}", type="primary", width="stretch"):
        with st.spinner("Checking with Scam Shield..."):
            pay(customer.name, S["payee_id"], S["amount"], S["hour"])
        st.rerun()


def _summary_line() -> None:
    st.caption(f"Paying **{inr(S['amount_paid'])}** at {hour_label(S['hour_paid'])}")


def _behind_the_scenes() -> None:
    st.markdown("#### Behind the scenes")
    st.caption("What the bank's backend sees. The customer never sees this panel.")
    check = S.get("check")
    if not check:
        st.info("Make a payment to see Scam Shield's checks here.")
        return
    t = S.get("timings", {})
    st.markdown(f"**1 · Money check** ({t.get('money_s', 0):.1f}s)")
    st.progress(min(check["money_score"], 1.0), text=f"Money score {check['money_score']:.2f}")
    for reason in check["reasons"] or ["Nothing unusual for this customer"]:
        st.markdown(f"- {reason}")
    st.markdown(f"Decision: **{check['decision']}**")

    final = S.get("final")
    if final:
        took, source = t.get("context_s", 0), final["context_source"]
        st.markdown(f"**2 · Context check** ({took:.1f}s, {source})")
        st.progress(min(final["context_score"], 1.0),
                    text=f"Context score {final['context_score']:.2f}")
        st.progress(min(final["combined_score"], 1.0),
                    text=f"Combined {final['combined_score']:.2f} (hold at 0.70)")
        st.markdown(f"Scam type: **{final['scam_name']}** · Decision: **{final['decision']}**")
    with st.expander("Raw API responses"):
        st.json({"check-payment": check, "context": final})
