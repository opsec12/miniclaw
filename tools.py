"""
Tool definitions for MiniClaw — a very simple, local personal assistant.

Design choice: only a handful of tools, and the two genuinely risky ones
(run_shell, write_file) are OFF by default. Set ENABLE_DANGEROUS_TOOLS=1 to
turn them on. File tools are sandboxed to a single "workspace/" directory so
the model can't read or write anything else on your machine even when the
dangerous tools are enabled.

This is a deliberate contrast to projects like OpenClaw, which grant an
always-on agent broad system access (shell, browser, smart home) out of the
box — fine for a power user who understands the tradeoff, but not a sane
default for a "very simple" starter version.
"""

import os
import ast
import operator
import subprocess
import datetime
import requests

WORKSPACE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
os.makedirs(WORKSPACE, exist_ok=True)

DANGEROUS_TOOLS_ENABLED = os.environ.get("ENABLE_DANGEROUS_TOOLS", "0") == "1"


def _safe_path(path: str) -> str:
    """Resolve a user-supplied path and make sure it stays inside WORKSPACE."""
    resolved = os.path.abspath(os.path.join(WORKSPACE, path))
    if not resolved.startswith(WORKSPACE + os.sep) and resolved != WORKSPACE:
        raise ValueError(f"Path '{path}' escapes the workspace sandbox — refusing.")
    return resolved


# ---------------------------------------------------------------------------
# Safe tools (always on)
# ---------------------------------------------------------------------------

def get_time(**_) -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def web_fetch(url: str, **_) -> str:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "MiniClaw/0.1"})
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return f"Fetch failed: {exc}"
    text = resp.text
    return text[:4000] + ("... [truncated]" if len(text) > 4000 else "")


_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Unsupported expression")


def calculate(expression: str, **_) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        return str(result)
    except Exception as exc:
        return f"Could not evaluate '{expression}': {exc}"


def read_file(path: str, **_) -> str:
    try:
        safe = _safe_path(path)
        with open(safe, "r", errors="replace") as f:
            content = f.read(4000)
        return content
    except Exception as exc:
        return f"Read failed: {exc}"


# ---------------------------------------------------------------------------
# Dangerous tools (opt-in via ENABLE_DANGEROUS_TOOLS=1)
# ---------------------------------------------------------------------------

def write_file(path: str, content: str = "", **_) -> str:
    try:
        safe = _safe_path(path)
        with open(safe, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path} (inside workspace/)."
    except Exception as exc:
        return f"Write failed: {exc}"


def run_shell(command: str, **_) -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKSPACE, capture_output=True,
            text=True, timeout=15,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out[:4000] if out else "(no output)"
    except Exception as exc:
        return f"Command failed: {exc}"


SAFE_TOOLS = {
    "get_time": {
        "fn": get_time,
        "description": "Get the current local date and time. No arguments.",
        "args": {},
    },
    "web_fetch": {
        "fn": web_fetch,
        "description": "Fetch the text content of a URL.",
        "args": {"url": "string, the URL to fetch"},
    },
    "calculate": {
        "fn": calculate,
        "description": "Evaluate a basic math expression (+ - * / ** % //). No variables or functions.",
        "args": {"expression": "string, e.g. '12 * (3 + 4)'"},
    },
    "read_file": {
        "fn": read_file,
        "description": "Read a text file from the sandboxed workspace/ directory.",
        "args": {"path": "string, relative path inside workspace/"},
    },
}

DANGEROUS_TOOLS = {
    "write_file": {
        "fn": write_file,
        "description": "Write a text file into the sandboxed workspace/ directory (overwrites).",
        "args": {"path": "string, relative path inside workspace/", "content": "string, file contents"},
    },
    "run_shell": {
        "fn": run_shell,
        "description": "Run a shell command, working directory is the workspace/ sandbox. Use with caution.",
        "args": {"command": "string, the shell command to run"},
    },
}


def get_active_tools() -> dict:
    tools = dict(SAFE_TOOLS)
    if DANGEROUS_TOOLS_ENABLED:
        tools.update(DANGEROUS_TOOLS)
    return tools
