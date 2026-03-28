"""
Tool definitions and implementations for CarPi assistants.

TOOLS      — JSON schema list to pass to the model (session.update / tools param)
dispatch() — call this with a tool name + args dict to execute the right function
"""

import time
from ddgs import DDGS

# ---------------------------------------------------------------------------
# Schema definitions (what the model sees)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "name": "web_search",
        "description": (
            "Search the internet for current information, news headlines, recent events, "
            "facts you are uncertain about, or anything that may have changed since your training. "
            "Use this whenever the user asks about news, current events, live scores, prices, "
            "or anything that benefits from up-to-date information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up."
                }
            },
            "required": ["query"]
        }
    }
]

# Chat Completions format (used by gpt_pipeline.py)
TOOLS_CHAT = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
    }
    for t in TOOLS
]

# Anthropic format (used by main.py) — uses input_schema instead of parameters
TOOLS_ANTHROPIC = [
    {
        "name": t["name"],
        "description": t["description"],
        "input_schema": t["parameters"],
    }
    for t in TOOLS
]

# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

def web_search(query: str) -> str:
    print(f"🔍 Searching: {query}")
    t0 = time.perf_counter()
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "No results found."
        output = "\n\n".join(f"{r['title']}: {r['body']}" for r in results)
    except Exception as e:
        output = f"Search failed: {e}"
    print(f"⏱  Web search: {time.perf_counter() - t0:.2f}s")
    return output


# ---------------------------------------------------------------------------
# Dispatcher — maps tool name → function call
# ---------------------------------------------------------------------------

_REGISTRY = {
    "web_search": lambda args: web_search(args["query"]),
}


def dispatch(name: str, args: dict) -> str:
    fn = _REGISTRY.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return fn(args)
