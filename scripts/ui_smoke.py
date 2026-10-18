"""Click through the Demo Bank UI headlessly (Streamlit AppTest) against the running API
(SCAM_SHIELD_URL) and BigQuery. Use before a demo.

Usage: python -m scripts.ui_smoke
"""

import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGE = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from ui.views import demo_bank
demo_bank.page()
"""

# (scenario title, purpose label, on call, told to keep secret, sample screenshot, button, expect)
CASES = [
    ("Meera pays her grocer", None, False, False, None, None, "sent"),
    ("Meera and the 'CBI officer'", "Govt / police / KYC / tax", True, True,
     "Sample: 'CBI officer' chat", "Cancel payment", "cancelled"),
    ("Anita's 'KYC re-verification'", "Govt / police / KYC / tax", True, False,
     "Sample: KYC expiry SMS", "Call my bank", "helpline"),
    ("Rahul's 'task reward' deposit", "Job / task / reward", False, True,
     "Sample: job / task chat", "Continue anyway", "sent at your request"),
    ("Arjun buys a car", "Shopping / bill", False, False, None, None, "sent"),
]


def check(at: AppTest) -> None:
    if at.exception:
        raise RuntimeError(at.exception[0].message)


def run_case(page: str, title, purpose, on_call, secret, sample, button, expect) -> str:
    at = AppTest.from_file(page, default_timeout=90).run()
    at.selectbox(key="scenario").set_value(title).run()
    next(b for b in at.button if b.label.startswith("Pay ")).click().run()
    check(at)

    if at.radio:  # safety check shown
        q = {r.label: r for r in at.radio}
        q["What is this payment for?"].set_value(purpose)
        q["Is someone on a call with you right now?"].set_value("Yes" if on_call else "No")
        q["Were you told to keep this secret or act fast?"].set_value("Yes" if secret else "No")
        if sample:
            next(s for s in at.selectbox if s.label == "Screenshot").set_value(sample)
        next(b for b in at.button if b.label == "Continue").click().run()
        check(at)

    if button:  # warning shown
        warning = " ".join(e.value for e in at.error)
        next(b for b in at.button if b.label == button).click().run()
        check(at)
    else:
        warning = ""
    final = " ".join(m.value for m in [*at.success, *at.info, *at.warning])
    if expect not in final:
        raise AssertionError(f"expected {expect!r}, got {final!r}")
    return f"{warning} -> {final}".strip(" ->")


def main() -> int:
    failures = 0
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(PAGE)
    for case in CASES:
        try:
            print(f"OK  {case[0]:32} {run_case(f.name, *case)[:110]}")
        except Exception as e:  # report every case, then fail
            failures += 1
            print(f"BAD {case[0]:32} {e}")
    Path(f.name).unlink()
    return failures


if __name__ == "__main__":
    sys.exit(main())
