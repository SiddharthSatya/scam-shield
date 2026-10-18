"""End-to-end check of the running API on the 5 demo scenarios (real BigQuery + Gemini).

Usage: python -m scripts.smoke_api [base_url]   (default http://localhost:8080)
Exits non-zero if any scenario gets an unexpected decision.
"""

import sys
import time

import httpx

from scam_shield.settings import get_settings
from scam_shield.synthetic import demo_scenarios

# The honest answers each demo customer would tap, plus the message they would share.
TAPS = {
    "digital_arrest": {
        "purpose": "govt_police_kyc", "on_call": True, "told_to_keep_secret": True,
        "message_text": "CBI NOTICE: Your Aadhaar is linked to a money laundering case. "
                        "Transfer funds to the RBI safe account for verification today. "
                        "Do not tell anyone or you will be arrested.",
    },
    "job_task": {
        "purpose": "job_task_reward", "on_call": False, "told_to_keep_secret": True,
        "message_text": "Congrats! Task 7 done. Deposit Rs 40,000 to unlock your Rs 1,20,000 "
                        "earnings. Offer valid 1 hour only.",
    },
    "kyc_update": {
        "purpose": "govt_police_kyc", "on_call": True, "told_to_keep_secret": False,
        "message_text": "SBI: Your KYC has expired. Account will be blocked today. Move your "
                        "balance to the verification account to avoid freezing.",
    },
    "car_purchase": {"purpose": "shopping_bill", "on_call": False, "told_to_keep_secret": False},
}


def main(base_url: str) -> int:
    headers = {"X-API-Key": get_settings().api_key.get_secret_value()}
    failures = 0
    with httpx.Client(base_url=base_url, headers=headers, timeout=60) as http:
        for s in demo_scenarios():
            start = time.perf_counter()
            r = http.post("/v1/check-payment", json={
                "customer_id": s.customer_id, "payee_id": s.payee_id,
                "amount_inr": s.amount_inr, "hour_ist": s.hour_ist})
            r.raise_for_status()
            step1 = r.json()
            t1 = time.perf_counter() - start
            final, detail, t2 = step1["decision"], "", 0.0

            if step1["decision"] == "ask":
                start = time.perf_counter()
                r = http.post("/v1/context",
                              json={"token": step1["token"], **TAPS[s.scenario_id]})
                r.raise_for_status()
                step2 = r.json()
                t2 = time.perf_counter() - start
                final = step2["decision"]
                detail = (f" context={step2['context_score']:.2f} "
                          f"combined={step2['combined_score']:.2f} "
                          f"[{step2['scam_name']}, {step2['context_source']}]")

            ok = final == s.expected
            failures += not ok
            print(f"{'OK ' if ok else 'BAD'} {s.scenario_id:15} money={step1['money_score']:.2f} "
                  f"-> {step1['decision']:4} -> {final:5}{detail}  "
                  f"({t1:.1f}s + {t2:.1f}s)")
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"))
