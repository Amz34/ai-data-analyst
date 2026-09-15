"""Auto-dashboard: Plotly charts from a cleaned DataFrame."""
import json

import pandas as pd
import plotly.express as px


def build_charts(df: pd.DataFrame, max_cats: int = 5) -> list[dict]:
    charts = []
    # 1) categorical top-N bars (up to 2 categorical columns)
    cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])][:2]
    for c in cat_cols:
        counts = df[c].value_counts().head(max_cats)
        if len(counts) == 0:
            continue
        fig = px.bar(x=counts.index.astype(str), y=counts.values, title=f"Top {c}")
        charts.append(json.loads(fig.to_json()))

    # 2) numeric histograms (up to 3 numeric columns)
    num_cols = list(df.select_dtypes("number").columns)[:3]
    for c in num_cols:
        fig = px.histogram(df, x=c, title=f"Distribution of {c}")
        charts.append(json.loads(fig.to_json()))

    # 3) time series if a real date-like column exists (numeric columns are NOT dates)
    for c in list(df.columns)[:5]:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().sum() > max(2, int(len(df) * 0.8)):
            years = parsed.dt.year.dropna()
            if not years.between(1900, 2100).all():
                continue  # numeric-looking strings (e.g. "100") parse as ns since epoch
            tmp = df.copy()
            tmp["_dt"] = parsed
            y = num_cols[0] if num_cols else None
            if y is not None:
                fig = px.line(tmp.sort_values("_dt"), x="_dt", y=y, title=f"Trend by {c}")
                charts.append(json.loads(fig.to_json()))
            break
    return charts
