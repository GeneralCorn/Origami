"""Prompt for contextual retrieval — generates a compact context prefix for each PDF chunk."""

CONTEXTUALIZER_PROMPT = """\
<document>
{whole_document}
</document>

<chunk>
{chunk_content}
</chunk>

Task: Write 1–2 sentences that situate the chunk within the overall document so it can be retrieved in isolation.

Rules:
- Use only information supported by the document/chunk. Do not speculate or add new claims.
- Prefer concrete identifiers: section/topic, entities, method names, what is being defined/compared.
- Do not evaluate (avoid “better/worse”, “improves”, etc.) unless explicitly stated in the chunk.
- Output ONLY the context sentences. No bullets, no headings, no quotes, no extra text.
"""