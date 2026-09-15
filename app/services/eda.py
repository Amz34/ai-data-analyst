"""Auto-EDA: deterministic statistics over a cleaned DataFrame."""
import pandas as pd


import math


def _num(v, ndigits: int = 4):
    """JSON-safe number: NaN/Inf (empty or all-null columns) become None, not a 500."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, ndigits)


def compute_eda(df: pd.DataFrame) -> dict:
    cols = [str(c) for c in df.columns]
    numeric = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            numeric[str(c)] = {
                "mean": _num(s.mean()),
                "median": _num(s.median()),
                "std": _num(s.std()) if len(s) > 1 else 0.0,
                "min": _num(s.min()),
                "max": _num(s.max()),
                "sum": _num(s.sum()),
                "nulls": int(df[c].isna().sum()),
                "unique": int(df[c].nunique()),
            }
    categorical = []
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            vc = df[c].value_counts()
            categorical.append({
                "column": str(c),
                "unique": int(df[c].nunique()),
                "top": str(vc.index[0]) if len(vc) else None,
                "counts": {str(k): int(v) for k, v in vc.head(10).items()},
            })
    corr = {
        str(c): {str(k): _num(v, 3) for k, v in row.items()}
        for c, row in df.select_dtypes("number").corr().to_dict().items()
    }
    missing = {str(c): int(df[c].isna().sum()) for c in df.columns}
    return {
        "columns": cols,
        "rows": len(df),
        "numeric": numeric,
        "categorical": categorical,
        "correlations": corr,
        "missing": missing,
    }
