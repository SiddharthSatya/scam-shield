"""Ask Gemini to write a labelled pack of scam and genuine messages for testing the
context check. Output: data/scam_pack.jsonl (one message per line).

Usage: python -m scripts.make_scam_pack [--per-type 30]
"""

import argparse
import json
from pathlib import Path
from typing import Literal

from google.genai import types
from pydantic import BaseModel, Field

from scam_shield.gemini import get_client
from scam_shield.scam_types import DESCRIPTIONS, ScamType
from scam_shield.settings import get_settings

OUT = Path("data/scam_pack.jsonl")


class Message(BaseModel):
    channel: Literal["whatsapp", "sms", "call_transcript", "email"]
    language: Literal["en", "hinglish", "hi"]
    text: str = Field(description="The message exactly as the victim would see or hear it")


class Batch(BaseModel):
    messages: list[Message]


PROMPT = """You are building a test dataset for an Indian bank's scam-detection system.
Write {n} different, realistic messages of this kind:

{label}: {description}

Rules:
- Indian context (UPI, Aadhaar, PAN, INR amounts, Indian names and banks).
- Mix channels (WhatsApp, SMS, call transcript, email) and languages (English, Hinglish, Hindi).
- Vary length, tone and tactics. Some subtle, some obvious.
- Use only obviously fake placeholders for links and numbers (e.g. bit.ly/xxxx, +91-98XXXXXX12).
- Never use a real person's name with a real role, or a real working URL.
"""


def generate(scam_type: ScamType, n: int) -> list[dict]:
    settings = get_settings()
    client = get_client(settings, timeout_ms=120_000)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=PROMPT.format(n=n, label=scam_type.value, description=DESCRIPTIONS[scam_type]),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Batch,
            temperature=1.0,
        ),
    )
    batch = response.parsed
    if not isinstance(batch, Batch):
        raise RuntimeError(f"Gemini returned no parsable batch for {scam_type}")
    return [{"label": scam_type.value, **m.model_dump()} for m in batch.messages]


def main(per_type: int) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for scam_type in ScamType:
        n = per_type * 2 if scam_type is ScamType.NONE else per_type
        batch = generate(scam_type, n)
        rows.extend(batch)
        print(f"{scam_type.value}: {len(batch)} messages")
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} messages to {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-type", type=int, default=30)
    main(parser.parse_args().per_type)
