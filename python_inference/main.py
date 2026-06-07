from __future__ import annotations

import argparse
from pathlib import Path

from config.loader import load_config
from orchestration.runner import InferenceRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run configurable missing-value inference")
    parser.add_argument("--config", required=True, help="Path to source YAML config")
    parser.add_argument("--input", help="Optional CSV path overriding the configured input source")
    parser.add_argument(
        "--parser-run-id",
        help="Optional MongoDB parser run id. Overrides automatic latest-completed selection.",
    )
    parser.add_argument(
        "--mode",
        choices=["evaluation", "production"],
        help="Optional inference mode overriding inference.mode from YAML.",
    )
    parser.add_argument("--target", action="append", dest="targets", help="Run only this inference target. Can be repeated.")
    parser.add_argument("--algorithm", action="append", dest="algorithms", help="Run only this algorithm. Can be repeated.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))
    summary = InferenceRunner(config).run(
        input_override=args.input,
        only_targets=set(args.targets) if args.targets else None,
        only_algorithms=set(args.algorithms) if args.algorithms else None,
        parser_run_id_override=args.parser_run_id,
        mode_override=args.mode,
    )

    print("\nInference run completed")
    print(f"- Source: {summary['source']}")
    print(f"- Mode: {summary['mode']}")
    print(f"- Input: {summary['input_source']}")
    if summary.get("parser_run_id"):
        print(f"- Parser run: {summary['parser_run_id']}")
    if summary.get("inference_run_id"):
        print(f"- Inference run: {summary['inference_run_id']}")
    if summary.get("final_permits_cloned") is not None:
        print(f"- Final permits cloned: {summary['final_permits_cloned']}")
    print(f"- Prepared rows: {summary['prepared_row_count']}")


if __name__ == "__main__":
    main()
