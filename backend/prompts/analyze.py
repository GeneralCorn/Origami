"""Prompt for the analyze node — extracts findings from retrieved chunks."""

ANALYZE_PROMPT = """\
You are a research analyst. Analyze these document excerpts to answer the user's question.

## User's Question
{current_query}

## Current Research Notes
{current_notes}

## Retrieved Document Excerpts
Each excerpt opens with a header naming its source and saying whether its text
is verbatim from that source or was written by a model about it.

{chunks_text}

## User's Active Notes (for context)
{active_notes}

Extract specific facts, data points, and key findings that help answer the question.
If you find relevant information, list each finding as a separate bullet point.
If the excerpts don't contain relevant information, say "NO_RELEVANT_INFO".
Be precise and cite specific details from the excerpts.
Text marked WRITTEN BY A MODEL is a description of the source, not a quotation
from it. Never state it as a fact about the source, and never quote it as if
someone had written it; attribute it, as in "the description of X says ..."."""
