"""Input adapters for inference datasets."""

from data_loading.loader import load_dataset
from data_loading.loader_types import LoadedDataset

__all__ = ["LoadedDataset", "load_dataset"]
