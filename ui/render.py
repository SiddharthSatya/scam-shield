"""Generic renderer for Scam Shield's server-driven screens.

Nothing here knows about specific questions: it draws whatever the API sends.
That is the point of the demo: a bank adds Scam Shield with one generic screen.
"""

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

ASSETS = Path(__file__).parent / "assets"
SAMPLE_SCREENSHOTS = {
    "Sample: 'CBI officer' chat": "digital_arrest.png",
    "Sample: job / task chat": "job_task.png",
    "Sample: KYC expiry SMS": "kyc_update.png",
}
NO_UPLOAD = "No screenshot"
OWN_UPLOAD = "Upload my own"
BUTTON_TYPE = {"primary": "primary", "danger": "secondary", "secondary": "secondary"}


@dataclass(frozen=True)
class Answers:
    """Taps and attachments collected from a safety-check screen."""
    values: dict[str, Any]
    message_text: str | None
    image_base64: str | None
    image_mime_type: str


def safety_check(screen: dict[str, Any], key: str) -> Answers | None:
    """Draw a safety-check screen. Returns answers once the customer submits."""
    st.subheader(screen["title"])
    if screen.get("body"):
        st.caption(screen["body"])

    values: dict[str, Any] = {}
    text, image, mime = None, None, "image/png"
    with st.form(key=f"{key}-form", border=False):
        for q in screen.get("questions", []):
            qkey = f"{key}-{q['id']}"
            if q["kind"] == "single_choice":
                labels = {o["label"]: o["value"] for o in q["options"]}
                choice = st.radio(q["text"], list(labels), index=None, key=qkey)
                values[q["id"]] = labels.get(choice) if choice else None
            elif q["kind"] == "yes_no":
                choice = st.radio(q["text"], ["Yes", "No"], index=None, horizontal=True,
                                  key=qkey)
                values[q["id"]] = None if choice is None else choice == "Yes"
            elif q["kind"] == "upload_optional":
                st.markdown(f"**{q['text']}**")
                source = st.selectbox("Screenshot", [NO_UPLOAD, *SAMPLE_SCREENSHOTS, OWN_UPLOAD],
                                      key=f"{qkey}-src", label_visibility="collapsed")
                uploaded = st.file_uploader("Your screenshot", type=["png", "jpg", "jpeg"],
                                            key=f"{qkey}-file") if source == OWN_UPLOAD else None
                text = st.text_area("Or paste the message text (optional)", key=f"{qkey}-text",
                                    max_chars=5_000) or None
                image, mime = _image_from(source, uploaded)

        labels = [b["label"] for b in screen.get("buttons", []) if b["action"] == "submit"]
        submitted = st.form_submit_button(labels[0] if labels else "Continue", type="primary",
                                          width="stretch")
    if not submitted:
        return None
    return Answers(values=values, message_text=text, image_base64=image, image_mime_type=mime)


def _image_from(source: str, uploaded) -> tuple[str | None, str]:
    if source in SAMPLE_SCREENSHOTS:
        data = (ASSETS / SAMPLE_SCREENSHOTS[source]).read_bytes()
        return base64.b64encode(data).decode(), "image/png"
    if uploaded is not None:
        mime = "image/jpeg" if uploaded.type in ("image/jpeg", "image/jpg") else "image/png"
        return base64.b64encode(uploaded.getvalue()).decode(), mime
    return None, "image/png"


def alert(screen: dict[str, Any], key: str) -> str | None:
    """Draw a warning or cooling-off screen. Returns the chosen button action, if any."""
    box = st.error if screen["kind"] == "warning" else st.warning
    with st.container(border=True):
        icon = "⛔" if screen["kind"] == "warning" else "⏳"
        st.subheader(f"{icon} {screen['title']}")
        if screen.get("scam_name"):
            box(f"**Scam alert: {screen['scam_name']}**")
        if screen.get("body"):
            st.write(screen["body"])
        if screen.get("bullets"):
            st.markdown("**What gave it away**")
            st.markdown("\n".join(f"- {b}" for b in screen["bullets"]))

        chosen = None
        for b in screen.get("buttons", []):
            if st.button(b["label"], key=f"{key}-{b['action']}", type=BUTTON_TYPE[b["style"]],
                         width="stretch"):
                chosen = b["action"]
    return chosen
