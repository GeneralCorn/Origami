"""
Prompt templates for the Origami research agent pipeline.

All LLM prompts live here so they can be edited independently of code logic.
"""

from prompts.analyze import ANALYZE_PROMPT
from prompts.review import REVIEW_PROMPT
from prompts.final_response import FINAL_RESPONSE_WITH_ACTIONS_PROMPT, CHAT_ONLY_INSTRUCTION, EDIT_ALLOWED_INSTRUCTION
from prompts.contextualizer import CONTEXTUALIZER_PROMPT
from prompts.title import TITLE_PROMPT

__all__ = [
    "ANALYZE_PROMPT",
    "REVIEW_PROMPT",
    "FINAL_RESPONSE_WITH_ACTIONS_PROMPT",
    "CHAT_ONLY_INSTRUCTION",
    "EDIT_ALLOWED_INSTRUCTION",
    "CONTEXTUALIZER_PROMPT",
    "TITLE_PROMPT",
]
