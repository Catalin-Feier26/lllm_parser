from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LoadedDataset:
    """A normalized tabular dataset plus its provenance-aware identity."""

    dataframe: pd.DataFrame
    input_name: str
    input_description: str
    parser_run_id: str | None = None
