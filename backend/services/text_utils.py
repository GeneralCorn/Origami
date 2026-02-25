"""Shared text utilities for the backend services."""

import re
import unicodedata

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from LLM output."""
    return _THINK_TAG_RE.sub("", text).strip()


# Common filler words to drop when shortening titles
_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with",
    "by", "from", "is", "are", "was", "were", "that", "this", "its",
    "using", "via", "based", "towards", "toward",
    "all", "you", "we", "how", "what", "why", "when", "do", "does",
    "need", "new", "can", "not", "no", "as", "at", "it", "be", "so",
    "about", "into", "over", "through", "between", "more", "most",
    "really", "very", "also", "some", "any", "each", "every",
    "large", "small", "simple", "better", "beyond",
}

# Words that commonly abbreviate in academic/technical titles
_ACRONYMS: dict[str, str] = {
    "language": "lang",
    "model": "model",
    "models": "models",
    "learning": "learning",
    "network": "net",
    "networks": "nets",
    "neural": "neural",
    "generation": "gen",
    "generative": "gen",
    "representation": "repr",
    "representations": "reprs",
    "reinforcement": "rl",
    "optimization": "optim",
    "transformer": "transformer",
    "transformers": "transformers",
    "attention": "attn",
    "classification": "cls",
    "recognition": "recog",
    "detection": "detect",
    "information": "info",
    "knowledge": "knowledge",
    "retrieval": "retrieval",
    "calibration": "calib",
    "evaluation": "eval",
    "implicit": "implicit",
    "explicit": "explicit",
    "efficient": "efficient",
    "consistently": "consistent",
    "consistency": "consistency",
    "architecture": "arch",
    "implementation": "impl",
    "performance": "perf",
    "application": "app",
    "applications": "apps",
    "distribution": "dist",
    "approximate": "approx",
    "probabilistic": "prob",
    "statistical": "stat",
    "energy": "energy",
    "inference": "infer",
    "training": "train",
    "pre-training": "pretrain",
    "pretraining": "pretrain",
    "fine-tuning": "finetune",
    "finetuning": "finetune",
    "reasoning": "reasoning",
    "chain-of-thought": "cot",
    "chain of thought": "cot",
    "temperature": "temp",
    "experiment": "exp",
    "experimental": "exp",
    "benchmark": "bench",
    "analysis": "analysis",
    "framework": "framework",
    "algorithm": "algo",
    "algorithms": "algos",
    "database": "db",
    "introduction": "intro",
    "convolutional": "conv",
    "recurrent": "recurrent",
    "adversarial": "adv",
    "prediction": "pred",
    "processing": "proc",
    "embedding": "embed",
    "embeddings": "embeds",
    "multi-modal": "multimodal",
    "multimodal": "multimodal",
    "augmented": "aug",
    "intensive": "intensive",
    "knowledge-intensive": "knowledge-intensive",
    "bidirectional": "bidir",
    "understanding": "understanding",
    "segmentation": "seg",
    "summarization": "summ",
    "translation": "translation",
    "sequence": "seq",
    "sequences": "seqs",
    "question": "qa",
    "answering": "ans",
    "question-answering": "qa",
    "autonomous": "auto",
    "automatically": "auto",
    "automatic": "auto",
    "deep": "deep",
    "residual": "res",
    "diffusion": "diff",
    "contrastive": "contrastive",
    "self-supervised": "ssl",
    "semi-supervised": "semi-sup",
    "unsupervised": "unsup",
    "supervised": "sup",
    "instruction": "instruct",
    "alignment": "align",
    "scaling": "scaling",
    "parameter": "param",
    "parameters": "params",
    "stochastic": "stoch",
    "variational": "var",
    "compositional": "comp",
    "constitutional": "const",
    "harmlessness": "safety",
    "feedback": "fb",
}


def shorten_title(title: str, max_words: int = 5) -> str:
    """Condense a long title to ~5 key words with abbreviations."""
    # Strip subtitle after colon/dash
    for sep in [":", " - ", " — ", " – "]:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    words = title.split()

    # Try multi-word phrases first (e.g. "chain of thought" -> "cot")
    title_lower = " ".join(w.lower().strip(".,;()[]") for w in words)
    for phrase, abbrev in _ACRONYMS.items():
        if " " in phrase and phrase in title_lower:
            title_lower = title_lower.replace(phrase, abbrev)
    words = title_lower.split()

    # Drop stopwords, abbreviate known terms
    kept: list[str] = []
    for w in words:
        lower = w.strip(".,;()[]")
        if lower in _STOPWORDS:
            continue
        abbrev = _ACRONYMS.get(lower, lower)
        kept.append(abbrev)

    # Take first max_words (count hyphenated parts as multiple words)
    final: list[str] = []
    count = 0
    for k in kept:
        parts = len(k.split("-"))
        if count + parts > max_words and final:
            break
        final.append(k)
        count += parts

    return " ".join(final) if final else title.split()[0]


def sanitize_filename(name: str) -> str:
    """Convert a human-readable name into a safe filename slug."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:80] if name else "untitled"
