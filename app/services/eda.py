"""Auto-EDA: deterministic statistics over a cleaned DataFrame."""
import pandas as pd


def compute_eda(df: pd.DataFrame) -> dict:
    cols = [str(c) for c in df.columns]
    numeric = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            numeric[str(c)] = {
                "mean": round(float(s.mean()), 4) if len(s) else 0.0,
                "median": round(float(s.median()), 4) if len(s) else 0.0,
                "std": round(float(s.std()), 4) if len(s) > 1 else 0.0,
                "min": float(s.min()) if len(s) else 0.0,
                "max": float(s.max()) if len(s) else 0.0,
                "sum": float(s.sum()),
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
    corr = df.select_dtypes("number").corr().round(3).to_dict()
    missing = {str(c): int(df[c].isna().sum()) for c in df.columns}
    return {
        "columns": cols,
        "rows": len(df),
        "numeric": numeric,
        "categorical": categorical,
        "correlations": corr,
        "missing": missing,
    }
