# MiniClaw

A very simple, local, tool-using personal assistant — the stripped-down idea
behind projects like [OpenClaw](https://github.com/opsec12/openclaw), minus
the 50+ integrations, auto-generated skills, and always-on system access.
Runs entirely through [Ollama](https://ollama.com) on your own machine.

## What it can do

A small, fixed set of tools instead of an open-ended skill marketplace:

**On by default (safe):**
- `get_time` — current date/time
- `web_fetch` — fetch a URL's text content
- `calculate` — basic math, no arbitrary code execution
- `read_file` — read a file, sandboxed to `workspace/`

**Off by default (opt-in):**
- `write_file` — write a file, sandboxed to `workspace/`
- `run_shell` — run a shell command, cwd is `workspace/`

Enable the dangerous tools only if you understand the tradeoff:

```bash
ENABLE_DANGEROUS_TOOLS=1 python app.py
```

This mirrors a real concern called out about OpenClaw itself: broad
permissions plus an unvetted skill marketplace is a genuine security risk for
an always-on agent. MiniClaw defaults to the opposite — nothing risky runs
unless you explicitly turn it on, and file access never leaves the
`workspace/` sandbox even when it is on.

## Setup

```bash
ollama pull llama3.1
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5001](http://localhost:5001).

Tool-calling reliability depends on the model — `llama3.1`, `qwen2.5`, and
`mistral-nemo` follow the "respond with a tool-call JSON object" instruction
much more consistently than base `llama3`. If tool calls seem to misfire,
switch models:

```bash
OLLAMA_MODEL=qwen2.5 python app.py
```

## How it works

No native function-calling API dependency — just a system prompt telling the
model the available tools and asking it to respond with a JSON object to
call one, or plain text for a final answer. `app.py` loops: send the
conversation to Ollama, check if the reply is a tool call, run the tool if
so, feed the result back in, repeat (capped at 5 hops to avoid infinite
loops), until the model responds with plain text.

## Project structure

```
miniclaw/
├── app.py              # Flask backend, chat loop
├── tools.py             # Tool definitions + safety gating
├── templates/index.html # Chat UI
├── workspace/            # Sandbox directory for file tools
└── requirements.txt
```
