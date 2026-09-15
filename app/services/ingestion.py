"""Dataset ingestion: read, clean, persist."""
import io
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def validate_filename(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only CSV or Excel files are supported")
    return ext


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, drop blank rows + exact duplicates, coerce numerics."""
    df = df.copy()
    # strip string whitespace (NaN-safe)
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
            mask = df[col].notna()
            df.loc[mask, col] = (
                df.loc[mask, col].astype(str).str.strip().replace("", pd.NA)
            )
    # drop fully-blank rows
    df = df.dropna(how="all")
    # drop exact duplicates (after stripping)
    df = df.drop_duplicates()
    # numeric columns: empties -> 0.0; object columns that look numeric -> float
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].fillna(0.0).astype("float64")
        elif df[col].dtype == object:
            coerced = pd.to_numeric(df[col], errors="ignore")
            if coerced.dtype.kind in "iuf":
                df[col] = coerced.fillna(0.0).astype("float64")
    return df.reset_index(drop=True)


def load_clean_bytes(data: bytes, filename: str) -> pd.DataFrame:
    ext = validate_filename(filename)
    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))
    return clean(df)
