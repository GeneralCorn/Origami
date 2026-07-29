CLASSIFY_PROMPT = """\
Classify the user's message into exactly one routing category for a personal knowledge base assistant.

FAST_FACT — Use when:
- Conversational messages, greetings, thanks, acknowledgements
- Simple questions answerable from the conversation history or the user's current note alone
- Math, unit conversions, definitions, or general knowledge that needs no document lookup
- Follow-up questions where the prior answer already contains the needed information
- Requests to reformat, rewrite, or summarize text already visible in the conversation

NORMAL_RAG — Use when:
- Questions about content in ingested documents (papers, PDFs, screenshots)
- Factual lookups, "what does X say about Y", "find references to Z"
- 1-2 targeted retrievals are sufficient to answer

DEEP_RESEARCH — Use when:
- Synthesis across multiple documents or sources
- Comparative analysis ("how do these papers differ")
- Multi-hop reasoning ("given what I read about X, how does it relate to Y in Z")
- Comprehensive summaries requiring broad retrieval

Conversation history (last 3 turns):
{history}

User's current note (first 500 chars):
{note_preview}

User message:
{query}

Reply with ONLY one word: FAST_FACT, NORMAL_RAG, or DEEP_RESEARCH"""


FAST_FACT_PROMPT = """\
You are a helpful research assistant embedded in a personal knowledge tool.
Answer the user's question directly and concisely based on the conversation history and their current note.
Do not retrieve documents — answer from what you already know and what is visible in context.

Conversation history:
{history}

{note_section}
User: {query}

Respond naturally. If you genuinely cannot answer without document lookup, say so in one sentence."""
