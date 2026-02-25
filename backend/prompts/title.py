"""Prompt for PDF title generation — suggests a filename from document content."""

TITLE_PROMPT = """\
Here is the beginning of a PDF document:
<text>
{text_preview}
</text>

Generate a very short filename (3-5 words max, no file extension) that captures the CORE METHOD or MAIN CONTRIBUTION of this paper. Focus on what makes it unique, not generic descriptors.

Rules:
- Use standard abbreviations: cot, rl, llm, nlp, gan, vae, bert, gpt, rag, ebm, ssl, conv, attn, etc.
- Use lowercase words separated by hyphens
- Prefer the novel technique/model name over the problem it solves
- If the paper has a named method (e.g. "LoRA", "FlashAttention"), use that as the core

Examples:
- "Attention Is All You Need" → attention-is-all-you-need
- "LoRA: Low-Rank Adaptation of Large Language Models" → lora-llm-adaptation
- "Think Consistently, Reason Efficiently: Energy-Based Calibration for Implicit CoT" → energy-based-cot-calib
- "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" → rag-knowledge-nlp
- "Denoising Diffusion Probabilistic Models" → denoising-diffusion-models

Output ONLY the filename, nothing else."""
