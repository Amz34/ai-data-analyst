"""Chat-to-data helpers: LLM code generation prompt + deterministic fallback."""
import pandas as pd

SYSTEM_PROMPT = (
    "You are a pandas expert. Given a DataFrame `df`, write ONLY python code (no imports, "
    "no print, no comments) that answers the user's question. Assign the final answer to a "
    "variable named `result`. If the answer is an aggregation, prefer a dict (e.g. "
    "result = df.groupby('col')['num'].sum().to_dict()) or a plain number."
)


def build_user_prompt(df: pd.DataFrame, question: str) -> str:
    cols = ", ".join(str(c) for c in df.columns)
    sample = df.head(3).to_dict(orient="records")
    return (
        f"DataFrame `df` has columns: {cols} and {len(df)} rows.\n"
        f"Sample rows: {sample}\n"
        f"Question: {question}\n"
        "Code:"
    )


def fallback_answer(df: pd.DataFrame, question: str) -> tuple[dict, str]:
    q = question.lower()
    nums = list(df.select_dtypes("number").columns)
    if any(w in q for w in ("average", "avg", "mean", "median")):
        tag = "median" if "median" in q else "mean"
        return {c: round(float(getattr(df[c], tag)()), 4) for c in nums}, f"fallback: {tag}"
    if any(w in q for w in ("sum", "total")):
        return {c: float(df[c].sum()) for c in nums}, "fallback: sum"
    if "max" in q or "highest" in q:
        return {c: float(df[c].max()) for c in nums}, "fallback: max"
    if "min" in q or "lowest" in q:
        return {c: float(df[c].min()) for c in nums}, "fallback: min"
    if any(w in q for w in ("count", "how many", "rows")):
        return {"rows": len(df), "columns": list(df.columns)}, "fallback: describe"
    return {"rows": len(df), "columns": list(df.columns)}, "fallback: describe"


def normalize_result(v):
    if isinstance(v, pd.Series):
        return v.to_dict()
    if isinstance(v, pd.DataFrame):
        return v.head(5).to_dict(orient="records")
    if hasattr(v, "item"):
        try:
            return v.item()
        except ValueError:
            return v.tolist()
    if hasattr(v, "tolist"):
        return v.tolist()
    return v
