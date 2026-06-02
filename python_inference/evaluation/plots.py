from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


def save_confusion_matrix_plot(
	confusion_matrix: list[list[int]],
	labels: list[str],
	output_path: Path,
	config: dict[str, Any] | None = None,
) -> None:
	"""Save a confusion-matrix plot using optional display settings.

	Supported config values:
	- title
	- xlabel
	- ylabel
	- figure_width
	- figure_height
	- dpi
	- x_label_rotation
	"""
	config = config or {}

	title = config.get("title", "Confusion Matrix")
	xlabel = config.get("xlabel", "Predicted label")
	ylabel = config.get("ylabel", "True label")
	figure_width = config.get("figure_width", 8)
	figure_height = config.get("figure_height", 6)
	dpi = config.get("dpi", 150)
	x_label_rotation = config.get("x_label_rotation", 30)

	cm = np.array(confusion_matrix)

	if cm.ndim != 2:
		raise ValueError("confusion_matrix must be a two-dimensional list")

	if cm.shape != (len(labels), len(labels)):
		raise ValueError(
			"Confusion-matrix dimensions must match the number of labels: "
			f"matrix={cm.shape}, labels={len(labels)}"
		)

	fig, ax = plt.subplots(figsize=(figure_width, figure_height))
	im = ax.imshow(cm, interpolation="nearest", cmap="Greys")
	fig.colorbar(im, ax=ax)

	ax.set(
		xticks=np.arange(len(labels)),
		yticks=np.arange(len(labels)),
		xticklabels=labels,
		yticklabels=labels,
		title=title,
		ylabel=ylabel,
		xlabel=xlabel,
	)

	plt.setp(
		ax.get_xticklabels(),
		rotation=x_label_rotation,
		ha="right",
		rotation_mode="anchor",
	)

	threshold = cm.max() / 2.0 if cm.size > 0 else 0
	for i in range(cm.shape[0]):
		for j in range(cm.shape[1]):
			ax.text(
				j,
				i,
				str(cm[i, j]),
				ha="center",
				va="center",
				color="white" if cm[i, j] > threshold else "black",
				fontsize=11,
				fontweight="bold",
			)

	fig.tight_layout()
	output_path.parent.mkdir(parents=True, exist_ok=True)
	fig.savefig(output_path, bbox_inches="tight", dpi=dpi)
	plt.close(fig)
