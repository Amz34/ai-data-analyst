"""Restricted pandas sandbox for chat-to-data.

Runs user code in a SEPARATE python process (subprocess + timeout):
- real OS-level kill on timeout (no GIL starvation),
- `__builtins__` whitelist WITHOUT `__import__` -> no imports inside exec,
- `df` and `pd` injected; result must be assigned to `result`,
- banned patterns (file/network/import) rejected before execution.

MVP isolation: pattern bans + process boundary. A stricter model
(namespaces/containers/OS user) is a documented P2 hardening step.
"""
import os
import pickle
import subprocess
import sys
import tempfile

BANNED = [
    "import os", "import subprocess", "import socket", "import requests",
    "import urllib", "import pathlib", "import shutil", "__import__",
    "open(", "to_csv", "to_excel", "to_pickle", "to_json", "read_csv",
    "read_excel", "read_pickle", "exec(", "eval(", "globals(", "locals(",
    "system(", "getattr", "setattr",
]

_WRAPPER = r"""
import builtins, pickle, sys
df_path, out_path = sys.argv[1], sys.argv[2]
with open(df_path, "rb") as f:
    df = pickle.load(f)
import pandas as pd
import io as _io
_capture = _io.StringIO()
_allowed = {k: v for k, v in vars(builtins).items() if k in {
    "len", "range", "str", "int", "float", "bool", "list", "dict", "tuple",
    "set", "sum", "min", "max", "abs", "round", "sorted", "zip", "enumerate",
    "any", "all", "isinstance", "ValueError", "KeyError", "TypeError",
    "Exception", "print",
}}
def _print(*a, **k):
    _capture.write(" ".join(str(x) for x in a) + "\n")
_allowed["print"] = _print
ns = {"df": df, "pd": pd, "__builtins__": _allowed, "result": None}
_code = sys.stdin.read()
try:
    exec(compile(_code, "<sandbox>", "exec"), ns)
except BaseException as e:
    print(type(e).__name__ + ": " + str(e), file=sys.stderr)
    sys.exit(1)


def _norm(v):
    # recursively convert pandas/numpy values to plain JSON-safe values
    if isinstance(v, pd.Series):
        return v.to_dict()
    if isinstance(v, pd.DataFrame):
        return v.head(5).to_dict(orient="records")
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, TypeError):
            pass
    if hasattr(v, "tolist"):
        return v.tolist()
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return v


try:
    with open(out_path, "wb") as f:
        pickle.dump(_norm(ns.get("result")), f)
except BaseException as e:
    print("result-not-picklable: " + str(e), file=sys.stderr)
    sys.exit(2)
print(_capture.getvalue(), end="")
"""


def run_code(code: str, df, timeout: int = 5) -> dict:
    for pat in BANNED:
        if pat in code:
            return {"ok": False, "error": f"Blocked pattern: {pat!r}", "result": None, "output": ""}
    with tempfile.TemporaryDirectory() as td:
        df_path = os.path.join(td, "df.pkl")
        out_path = os.path.join(td, "out.pkl")
        with open(df_path, "wb") as f:
            pickle.dump(df, f)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _WRAPPER, df_path, out_path],
                input=code,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={"PYTHONNOUSERSITE": "1"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Execution timeout", "result": None, "output": ""}
        if proc.returncode != 0:
            err = (proc.stderr or "").strip().splitlines()
            return {
                "ok": False,
                "error": err[-1] if err else "execution failed",
                "result": None,
                "output": proc.stdout,
            }
        result = None
        if os.path.exists(out_path):
            with open(out_path, "rb") as f:
                result = pickle.load(f)
        return {"ok": True, "result": result, "output": proc.stdout, "error": None}
