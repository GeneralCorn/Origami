"""Compare candidate embedding models on the retrieval this product actually does.

The corpus is English papers and Chinese notes about them, so the interesting
case is not same-language retrieval, which everything handles, but CROSS-lingual:
a Chinese query finding the English passage it refers to.

Two conventions are handled per family, and getting them wrong is the usual way
these comparisons come out backwards:

- e5 models are trained with "query: " and "passage: " prefixes and lose a lot
  of their quality without them.
- bge models want a retrieval instruction on the query side only.

Run from the backend directory so fastembed and its cache resolve:
    uv run python ../scripts/eval_embeddings.py
"""

import sys
import time

import numpy as np
from fastembed import TextEmbedding

# Only models that are local, permissively licensed, and small enough to ship.
# NV-Embed is excluded on licence: cc-by-nc-4.0 forbids commercial use, which
# an MIT application cannot inherit.
CANDIDATES = [
    ("BAAI/bge-small-en-v1.5", "bge"),
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "plain"),
    ("sentence-transformers/paraphrase-multilingual-mpnet-base-v2", "plain"),
    ("intfloat/multilingual-e5-large", "e5"),
]

PASSAGES = [
    "Energy-based models assign a scalar energy to each configuration, and reasoning is framed as navigating toward lower-energy latent states.",
    "The hinge-style contrastive loss trains the model to rank coherent latent thoughts below incoherent ones by a fixed margin.",
    "Contextual retrieval prefaces each chunk with a short blurb situating it in the whole document before the chunk is embedded.",
    "Full Disk Access on macOS is path-based rather than gated by a usage description key, so denial surfaces as EPERM rather than silence.",
    "Quantized ONNX exports are not output-preserving, so vectors from a quantized build differ slightly from the Torch reference.",
    "A vision language model describes each screenshot, and that description is stored beside the OCR text rather than replacing it.",
]

# (query, index of the passage it should retrieve, label)
QUERIES = [
    ("What is the energy function used for in reasoning?", 0, "en->en"),
    ("How is the contrastive loss constructed?", 1, "en->en"),
    ("Why prefix a chunk before embedding it?", 2, "en->en"),
    ("能量模型如何引导推理走向更低能量的状态？", 0, "zh->en"),
    ("对比损失是怎么训练的？", 1, "zh->en"),
    ("为什么要在嵌入之前给文本块加上下文说明？", 2, "zh->en"),
    ("macOS 的完全磁盘访问权限被拒绝时会怎样？", 3, "zh->en"),
    ("量化后的向量和原始模型输出一样吗？", 4, "zh->en"),
    ("截图的文字描述是否会覆盖 OCR 结果？", 5, "zh->en"),
]


def encode(model: TextEmbedding, texts: list[str], style: str, is_query: bool) -> np.ndarray:
    if style == "e5":
        texts = [f"{'query' if is_query else 'passage'}: {t}" for t in texts]
    elif style == "bge" and is_query:
        texts = [f"Represent this sentence for searching relevant passages: {t}" for t in texts]
    vectors = np.array(list(model.embed(texts)), dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def evaluate(name: str, style: str) -> dict:
    started = time.perf_counter()
    model = TextEmbedding(model_name=name)
    load_s = time.perf_counter() - started

    passage_vectors = encode(model, PASSAGES, style, is_query=False)
    query_vectors = encode(model, [q for q, _, _ in QUERIES], style, is_query=True)

    hits_at_1 = 0
    reciprocal = 0.0
    per_label: dict[str, list[int]] = {}
    for row, (_, target, label) in enumerate(QUERIES):
        ranked = np.argsort(-(query_vectors[row] @ passage_vectors.T))
        rank = int(np.where(ranked == target)[0][0]) + 1
        hits_at_1 += rank == 1
        reciprocal += 1.0 / rank
        per_label.setdefault(label, []).append(rank)

    return {
        "model": name,
        "load_s": load_s,
        "recall_at_1": hits_at_1 / len(QUERIES),
        "mrr": reciprocal / len(QUERIES),
        "cross_lingual_at_1": sum(r == 1 for r in per_label.get("zh->en", [])) / max(1, len(per_label.get("zh->en", []))),
        "same_lingual_at_1": sum(r == 1 for r in per_label.get("en->en", [])) / max(1, len(per_label.get("en->en", []))),
    }


def main() -> None:
    print(f"{len(QUERIES)} queries over {len(PASSAGES)} passages, {sum(1 for _, _, l in QUERIES if l == 'zh->en')} cross-lingual\n")
    results = []
    for name, style in CANDIDATES:
        try:
            results.append(evaluate(name, style))
        except Exception as exc:
            print(f"  {name}: FAILED  {type(exc).__name__}: {exc}", file=sys.stderr)

    header = f"{'model':<58} {'R@1':>6} {'MRR':>6} {'en->en':>7} {'zh->en':>7} {'load':>7}"
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda r: -r["mrr"]):
        print(
            f"{r['model']:<58} {r['recall_at_1']:>6.2f} {r['mrr']:>6.2f} "
            f"{r['same_lingual_at_1']:>7.2f} {r['cross_lingual_at_1']:>7.2f} {r['load_s']:>6.1f}s"
        )


main()
