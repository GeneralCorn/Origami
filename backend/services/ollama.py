import json
from typing import Any, AsyncGenerator

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-r1:7b"


async def stream_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream a chat completion from Ollama, parsing <think> tags into reasoning parts.

    Yields dicts with:
        {"type": "reasoning", "content": "..."}
        {"type": "text", "content": "..."}
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()

            in_think_block = False
            buffer = ""

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if data.get("done"):
                    # Flush remaining buffer
                    if buffer:
                        yield {
                            "type": "reasoning" if in_think_block else "text",
                            "content": buffer,
                        }
                        buffer = ""
                    break

                content = data.get("message", {}).get("content", "")
                if not content:
                    continue

                buffer += content

                # Parse <think> tags for reasoning extraction
                while True:
                    if not in_think_block:
                        # Look for <think> opening tag
                        think_start = buffer.find("<think>")
                        if think_start != -1:
                            # Emit text before <think>
                            before = buffer[:think_start]
                            if before:
                                yield {"type": "text", "content": before}
                            buffer = buffer[think_start + len("<think>"):]
                            in_think_block = True
                        else:
                            # No <think> tag found — emit safe portion
                            # Keep last few chars in case tag is split across chunks
                            safe_end = len(buffer) - 7  # len("<think>") - 1
                            if safe_end > 0:
                                yield {"type": "text", "content": buffer[:safe_end]}
                                buffer = buffer[safe_end:]
                            break
                    else:
                        # Look for </think> closing tag
                        think_end = buffer.find("</think>")
                        if think_end != -1:
                            # Emit reasoning content
                            reasoning = buffer[:think_end]
                            if reasoning:
                                yield {"type": "reasoning", "content": reasoning}
                            buffer = buffer[think_end + len("</think>"):]
                            in_think_block = False
                        else:
                            # Still inside think block — emit safe portion
                            safe_end = len(buffer) - 8  # len("</think>") - 1
                            if safe_end > 0:
                                yield {"type": "reasoning", "content": buffer[:safe_end]}
                                buffer = buffer[safe_end:]
                            break
