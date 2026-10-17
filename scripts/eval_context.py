"""Evaluate the context check on data/scam_pack.jsonl (message text only, no taps).

Reports: scam-vs-genuine detection at score >= threshold, scam-type accuracy,
and the worst misses. Writes per-message results to data/eval_context.jsonl.

Usage: python -m scripts.eval_context [--threshold 0.5] [--workers 8] [--limit N]
"""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scam_shield.context import ContextInput, read_context
from scam_shield.gemini import get_client
from scam_shield.scam_types import ScamType
from scam_shield.settings import get_settings

PACK = Path("data/scam_pack.jsonl")
OUT = Path("data/eval_context.jsonl")


def main(threshold: float, workers: int, limit: int | None) -> None:
    rows = [json.loads(line) for line in PACK.open(encoding="utf-8")][:limit]
    settings = get_settings()
    client = get_client(settings, timeout_ms=60_000)

    def check(row: dict) -> dict:
        result = read_context(ContextInput(message_text=row["text"]), client, settings.gemini_model)
        return {**row, "pred_type": result.scam_type.value, "score": result.score,
                "source": result.source}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(check, rows))

    with OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    none = ScamType.NONE.value
    is_scam = [r["label"] != none for r in results]
    flagged = [r["score"] >= threshold for r in results]
    tp = sum(s and f for s, f in zip(is_scam, flagged, strict=True))
    fp = sum(not s and f for s, f in zip(is_scam, flagged, strict=True))
    fn = sum(s and not f for s, f in zip(is_scam, flagged, strict=True))
    scams = [r for r in results if r["label"] != none]
    type_ok = sum(r["pred_type"] == r["label"] for r in scams)
    fallbacks = sum(r["source"] == "fallback" for r in results)

    print(f"Messages: {len(results)}  (fallbacks: {fallbacks})")
    print(f"Scams caught (recall):      {tp}/{tp + fn} = {tp / max(tp + fn, 1):.0%}")
    print(f"Genuine wrongly flagged:    {fp}/{len(results) - len(scams)}")
    print(f"Precision:                  {tp / max(tp + fp, 1):.0%}")
    type_rate = type_ok / max(len(scams), 1)
    print(f"Scam type named correctly:  {type_ok}/{len(scams)} = {type_rate:.0%}")
    print("Per type (correct / total):")
    totals = Counter(r["label"] for r in results)
    correct = Counter(r["label"] for r in results if r["pred_type"] == r["label"])
    for label, total in totals.items():
        print(f"  {label:15} {correct[label]}/{total}")
    misses = [r for r, s, f in zip(results, is_scam, flagged, strict=True) if s != f]
    for r in misses[:8]:
        print(f"  MISS [{r['label']} -> {r['pred_type']} {r['score']}] {r['text'][:110]!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    main(args.threshold, args.workers, args.limit)
