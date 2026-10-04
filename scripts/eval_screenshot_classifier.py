"""Score the local screenshot classifier against a labelled folder of screenshots.

Layout: one sub-folder per collection id, holding the screenshots that
belong there.

    eval/
      shows-to-watch/  IMG_0001.PNG  IMG_0002.PNG
      papers-to-read/  IMG_0003.PNG
      inbox/           IMG_0004.PNG      # things that should NOT be filed

Run from backend/ so the services import:

    uv run python ../scripts/eval_screenshot_classifier.py ../eval
    uv run python ../scripts/eval_screenshot_classifier.py ../eval --no-embedding
    uv run python ../scripts/eval_screenshot_classifier.py ../eval --floor 0.3

Prints per-collection precision and recall and a confusion matrix. Reads
text with whatever OCR engine ORIGAMI_OCR_ENGINE resolves to; never calls
the VLM, because the point is to measure the path that runs without it.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services import ocr as ocr_service  # noqa: E402
from services.classify_screenshot import classify, default_embedder  # noqa: E402
from services.collections import INBOX_ID, list_collections  # noqa: E402
from services.screen_text import content_lines  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path, help="folder with one sub-folder per collection id")
    parser.add_argument("--no-embedding", action="store_true", help="keywords only")
    parser.add_argument("--floor", type=float, default=None, help="override ORIGAMI_CLASSIFY_MIN_CONFIDENCE")
    parser.add_argument("--verbose", action="store_true", help="print every misfile with its scores")
    args = parser.parse_args()

    engine = ocr_service.current_engine()
    if engine is None:
        print("No OCR engine available; install the ocr-fallback extra or run on macOS.", file=sys.stderr)
        return 2
    print(f"OCR engine: {engine.name}")

    collections = list_collections()
    known = {c.id for c in collections}
    embedder = None if args.no_embedding else default_embedder()

    confusion: dict[str, Counter] = defaultdict(Counter)
    misfiles: list[tuple[str, str, str, float, str]] = []
    total = 0
    for folder in sorted(p for p in args.root.iterdir() if p.is_dir()):
        expected = folder.name
        if expected not in known:
            print(f"skipping {folder.name}: not a collection id ({', '.join(sorted(known))})")
            continue
        for image in sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES):
            result = engine.recognize(image)
            text = "\n".join(content_lines(result.line_texts))
            verdict = classify(text, collections, embedder=embedder, min_confidence=args.floor)
            confusion[expected][verdict.collection_id] += 1
            total += 1
            if verdict.collection_id != expected:
                misfiles.append((image.name, expected, verdict.collection_id, verdict.confidence, verdict.method))

    if not total:
        print("No screenshots found.")
        return 1

    ids = [c.id for c in collections if c.id in confusion or any(c.id in row for row in confusion.values())]
    width = max(len(i) for i in ids) + 2
    print("\nconfusion (rows = expected, columns = predicted)")
    print(" " * width + "".join(f"{i[:10]:>11}" for i in ids))
    for expected in ids:
        row = confusion.get(expected, Counter())
        print(f"{expected:<{width}}" + "".join(f"{row.get(pred, 0):>11}" for pred in ids))

    print("\nper collection")
    for cid in ids:
        tp = confusion[cid][cid]
        fn = sum(confusion[cid].values()) - tp
        fp = sum(confusion[other][cid] for other in ids if other != cid)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        print(f"  {cid:<{width}} precision {precision:5.2f}  recall {recall:5.2f}  n={tp + fn}")

    correct = sum(confusion[c][c] for c in ids)
    filed_wrong = sum(1 for _, exp, got, _, _ in misfiles if got != INBOX_ID)
    print(f"\naccuracy {correct}/{total} = {correct / total:.2f}; misfiled into a wrong collection: {filed_wrong}; sent to inbox instead: {len(misfiles) - filed_wrong}")

    if args.verbose and misfiles:
        print("\nmisfiles")
        for name, exp, got, conf, method in misfiles:
            print(f"  {name}: expected {exp}, got {got} ({conf:.2f}, {method})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
