from __future__ import annotations

import argparse
from pathlib import Path

from config.loader import load_config
from orchestration.runner import InferenceRunner


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run configurable missing-value inference")
	parser.add_argument("--config", required=True, help="Path to source YAML config")
	parser.add_argument("--input", help="Optional CSV path overriding source.input_csv")
	parser.add_argument(
		"--target",
		action="append",
		dest="targets",
		help="Run only this inference target. Can be repeated.",
	)
	parser.add_argument(
		"--algorithm",
		action="append",
		dest="algorithms",
		help="Run only this algorithm. Can be repeated.",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	config = load_config(Path(args.config))
	runner = InferenceRunner(config)
	summary = runner.run(
		input_override=args.input,
		only_targets=set(args.targets) if args.targets else None,
		only_algorithms=set(args.algorithms) if args.algorithms else None,
	)

	print("\nInference run completed")
	print(f"- Source: {summary['source']}")
	print(f"- Input: {summary['input_file']}")
	print(f"- Prepared rows: {summary['prepared_row_count']}")


if __name__ == "__main__":
	main()
