"""Prompt for contextual retrieval — generates context prefix for each PDF chunk."""

CONTEXTUALIZER_PROMPT = """\
<document>
{whole_document}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
