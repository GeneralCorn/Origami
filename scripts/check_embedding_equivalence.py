"""Quantify how far fastembed vectors diverge from the old stack.

The repo moved bge-small-en-v1.5 from sentence-transformers (Torch) to
fastembed (quantized ONNX). Quantization is not output-preserving, so
the vectors are expected to be close but not identical. This script
embeds a fixed sentence set with fastembed and compares against
scripts/embedding_reference.json, which stores the vectors the
sentence-transformers build produced for the same sentences.

Run from the repo root with only fastembed installed:

    cd backend && uv run python ../scripts/check_embedding_equivalence.py

A mean cosine similarity near 1.0 (>= 0.99) means retrieval quality is
effectively unchanged and existing Chroma data remains usable until the
per-segment re-embed lands.
"""

import json
import math
import sys
from pathlib import Path

from fastembed import TextEmbedding

REFERENCE_PATH = Path(__file__).resolve().parent / "embedding_reference.json"


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vector))


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (norm(a) * norm(b))


def main() -> int:
    if not REFERENCE_PATH.exists():
        sys.stderr.write(f"missing reference file: {REFERENCE_PATH}\n")
        return 1

    reference = json.loads(REFERENCE_PATH.read_text())
    sentences = reference["sentences"]
    reference_vectors = reference["vectors"]

    model = TextEmbedding(model_name=reference["model"])
    fastembed_vectors = [vector.tolist() for vector in model.embed(sentences)]

    print(f"model:     {reference['model']}")
    print(f"reference: {reference['source']} ({reference['dimensions']} dims)")
    print(f"sentences: {len(sentences)}")
    print()
    print(f"{'cosine':>8}  {'ref norm':>9}  {'fe norm':>8}  sentence")

    similarities = []
    for sentence, ref_vec, fe_vec in zip(sentences, reference_vectors, fastembed_vectors):
        similarity = cosine(ref_vec, fe_vec)
        similarities.append(similarity)
        print(f"{similarity:8.5f}  {norm(ref_vec):9.4f}  {norm(fe_vec):8.4f}  {sentence[:60]}")

    mean = sum(similarities) / len(similarities)
    print()
    print(f"mean cosine similarity: {mean:.5f}")
    print(f"min cosine similarity:  {min(similarities):.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
