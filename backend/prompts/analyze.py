"""Prompt for the analyze node — extracts findings from retrieved chunks."""

ANALYZE_PROMPT = """\
You are a research analyst. Analyze these document excerpts to answer the user's question.

## User's Question
{current_query}

## Current Research Notes
{current_notes}

## Retrieved Document Excerpts
{chunks_text}

## User's Active Notes (for context)
{active_notes}

Extract specific facts, data points, and key findings that help answer the question.
If you find relevant information, list each finding as a separate bullet point.
If the excerpts don't contain relevant information, say "NO_RELEVANT_INFO".
Be precise and cite specific details from the excerpts."""
