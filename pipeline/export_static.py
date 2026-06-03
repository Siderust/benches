"""Export benchmark results as static JSON for standalone/internal viewers.

Writes the following layout under ``<output>``:

  index.json
  latest/manifest.json
  latest/scorecard.json
  latest/experiments/<experiment_id>.json
  runs/<run_id>/manifest.json
  runs/<run_id>/scorecard.json
  runs/<run_id>/experiments/<experiment_id>.json

Usage:
  python3 -m pipeline.export_static [--output PATH] [--lab-root PATH]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import scorecard


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def _load_manifest(run_dir: Path) -> dict | None:
    """Return parsed manifest dict, or None if no manifest.json exists."""
    mf = run_dir / "manifest.json"
    if mf.is_file():
        try:
            return json.loads(mf.read_text())
        except Exception:
            return {}
    return None


def _is_exported_latest_bundle(run_dir: Path) -> bool:
    """Return true when latest_results already has the static bundle layout."""
    return (
        (run_dir / "scorecard.json").is_file()
        and (run_dir / "manifest.json").is_file()
        and (run_dir / "experiments").is_dir()
    )


def export(lab_root: Path, output_root: Path) -> dict:
    """Materialise the static JSON tree. Returns a small summary dict."""
    runs = scorecard.discover_runs(lab_root)
    # discover_runs returns persistent runs first then the "latest" mirror.
    summaries = scorecard.compute_summaries(runs)

    exported_runs: list[str] = []
    latest_summary = None

    for run_id, run_dir in runs:
        if run_id == "latest" and _is_exported_latest_bundle(run_dir):
            scorecard_path = run_dir / "scorecard.json"
            manifest_path = run_dir / "manifest.json"
            card = json.loads(scorecard_path.read_text())
            mf_dict = json.loads(manifest_path.read_text())
            base = output_root / "latest"
            base.mkdir(parents=True, exist_ok=True)
            shutil.copy2(scorecard_path, base / "scorecard.json")
            shutil.copy2(manifest_path, base / "manifest.json")
            exp_dst = base / "experiments"
            if exp_dst.exists():
                shutil.rmtree(exp_dst)
            shutil.copytree(run_dir / "experiments", exp_dst)
            latest_summary = {
                "run_id": mf_dict.get("run_id") or card.get("run_id") or run_id,
                "timestamp": card.get("timestamp") or mf_dict.get("timestamp"),
                "machine": card.get("machine") or mf_dict.get("machine"),
            }
            continue

        experiments = scorecard.load_run(run_dir)
        if not experiments:
            continue

        manifest = _load_manifest(run_dir)

        # Skip dated runs that have no manifest — they are partial/interrupted.
        # The "latest" mirror is kept even if the manifest is thin.
        if run_id != "latest" and not manifest:
            continue

        card = scorecard.compute_scorecard(run_id, experiments)
        mf_dict = manifest or {}

        if run_id == "latest":
            base = output_root / "latest"
            latest_summary = {
                "run_id": mf_dict.get("run_id") or run_id,
                "timestamp": card.get("timestamp"),
                "machine": card.get("machine"),
            }
        else:
            base = output_root / "runs" / run_id
            exported_runs.append(run_id)

        _write_json(base / "scorecard.json", card)
        _write_json(base / "manifest.json", mf_dict or {"run_id": run_id})

        exp_root = base / "experiments"
        for experiment, rows in experiments.items():
            payload = {
                "experiment": experiment,
                "run_id": mf_dict.get("run_id") or run_id,
                "rows": rows,
            }
            _write_json(exp_root / f"{experiment}.json", payload)

    index = {
        "schema_version": 1,
        "latest": latest_summary,
        "runs": [s for s in summaries if s["id"] != "latest"],
    }
    _write_json(output_root / "index.json", index)

    return {
        "lab_root": str(lab_root),
        "output_root": str(output_root),
        "runs_exported": exported_runs,
        "latest_present": latest_summary is not None,
        "index_run_count": len(index["runs"]),
    }


def main() -> None:
    here = Path(__file__).resolve()
    default_lab_root = here.parent.parent
    default_output = default_lab_root / "static_export"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, default=default_lab_root,
                        help=f"Lab repo root (default: {default_lab_root})")
    parser.add_argument("--output", type=Path, default=default_output,
                        help=f"Output directory (default: {default_output})")
    args = parser.parse_args()

    summary = export(args.lab_root, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
