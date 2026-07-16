"""
MiniClaw — a very simple, local, tool-using personal assistant.

Inspired by OpenClaw's core idea (a local AI assistant that can act, not just
chat) but deliberately stripped down: a handful of tools instead of 50+
integrations, no auto-generated skills, and the risky tools (shell, file
writes) are off by default. Runs entirely on your machine via Ollama.

Run:
    pip install -r requirements.txt
    ollama pull llama3.1        # tool-calling works best on 3.1+ / qwen2.5 etc.
    python app.py
    open http://localhost:5001
"""

import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template
from tools import get_active_tools, DANGEROUS_TOOLS_ENABLED

app = Flask(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
MAX_TOOL_HOPS = 5


def build_system_prompt() -> str:
    tools = get_active_tools()
    tool_lines = []
    for name, spec in tools.items():
        args_desc = ", ".join(f'{k} ({v})' for k, v in spec["args"].items()) or "none"
        tool_lines.append(f"- {name}({args_desc}): {spec['description']}")

    return f"""You are MiniClaw, a small local personal assistant. You can either answer \
directly, or use a tool when it would give a better/more accurate answer.

Available tools:
{chr(10).join(tool_lines)}

To call a tool, respond with ONLY a single JSON object on its own, nothing else:
{{"tool": "<tool_name>", "args": {{...}}}}

When you have enough information to answer the user (including after seeing a tool \
result), respond with plain natural language text — never JSON — as your final answer.
Only call one tool at a time. Don't call a tool you don't need."""


def strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def try_parse_tool_call(text: str):
    text = strip_code_fences(text)
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "tool" in data:
        return data
    return None


def call_ollama(messages):
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False,
              "options": {"temperature": 0.2}},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


@app.route("/")
def index():
    return render_template(
        "index.html",
        model=OLLAMA_MODEL,
        tools=get_active_tools(),
        dangerous_enabled=DANGEROUS_TOOLS_ENABLED,
    )


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []  # [{role, content}, ...] prior turns from the client

    if not user_message:
        return jsonify({"error": "Say something first."}), 400

    tools = get_active_tools()
    messages = [{"role": "system", "content": build_system_prompt()}]
    messages += history
    messages.append({"role": "user", "content": user_message})

    trace = []  # tool calls made this turn, so the UI can show its work

    for _ in range(MAX_TOOL_HOPS):
        try:
            raw = call_ollama(messages)
        except requests.exceptions.ConnectionError:
            return jsonify({
                "error": f"Can't reach Ollama at {OLLAMA_HOST}. Is it running? Try: ollama serve"
            }), 502
        except requests.exceptions.RequestException as exc:
            return jsonify({"error": f"Ollama request failed: {exc}"}), 502

        call = try_parse_tool_call(raw)
        if call is None:
            # Plain text = final answer
            return jsonify({
                "reply": raw.strip(),
                "trace": trace,
                "model": OLLAMA_MODEL,
            })

        name = call.get("tool")
        args = call.get("args") or {}
        if name not in tools:
            result = f"Unknown tool '{name}'. Available: {', '.join(tools.keys())}"
        else:
            try:
                result = tools[name]["fn"](**args)
            except Exception as exc:
                result = f"Tool '{name}' raised an error: {exc}"

        trace.append({"tool": name, "args": args, "result": str(result)[:1000]})
        messages.append({"role": "assistant", "content": json.dumps(call)})
        messages.append({"role": "user", "content": f"[Tool result for {name}]: {result}"})

    return jsonify({
        "reply": "Stopped after too many tool calls in a row — try rephrasing your request.",
        "trace": trace,
        "model": OLLAMA_MODEL,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
