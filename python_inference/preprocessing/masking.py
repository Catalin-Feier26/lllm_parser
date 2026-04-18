from __future__ import annotations

import numpy as np
import pandas as pd


def create_masked_eval_dataset(
    df: pd.DataFrame,
    target_clean_col: str = "permit_class_clean",
    mask_rate: float = 0.2,
    seed: int = 42,
) -> pd.DataFrame:
    if not 0 < mask_rate < 1:
        raise ValueError("mask_rate must be between 0 and 1")

    df = df.copy()

    if target_clean_col not in df.columns:
        raise ValueError(f"Missing target column: {target_clean_col}")

    df["permit_class_true"] = df[target_clean_col]
    df["permit_class_input"] = df[target_clean_col]
    df["is_masked"] = 0

    eligible_idx = df.index[df[target_clean_col].notna()].tolist()
    if not eligible_idx:
        raise ValueError("No non-missing target rows available for masking")

    rng = np.random.default_rng(seed)
    mask_count = max(1, int(len(eligible_idx) * mask_rate))
    masked_idx = rng.choice(eligible_idx, size=mask_count, replace=False)

    df.loc[masked_idx, "permit_class_input"] = pd.NA
    df.loc[masked_idx, "is_masked"] = 1

    return df