import json
import sys


def run_kepler_solver(lines_iter):
    """Removed — Astropy has no public Kepler-equation solver.

    Reading the experiment input still consumes the expected number of
    lines so the orchestrator's stdin protocol stays in sync, but the
    result JSON declares the experiment unsupported.  The capability
    catalog also drops this row from the public scoreboard.
    """
    n = int(next(lines_iter).strip())
    for _ in range(n):
        next(lines_iter)
    result = {
        "experiment": "kepler_solver",
        "library": "astropy",
        "model": "unsupported",
        "status": "unsupported",
        "reason": (
            "Astropy does not expose a public Kepler-equation solver; "
            "row is excluded by the capability catalog."
        ),
        "count": 0,
        "cases": [],
    }
    json.dump(result, sys.stdout, indent=None)
    print()

def _legacy_run_kepler_solver_DELETED(lines_iter):
    """Removed Newton-Raphson solver (audit: fabricated upstream API).

    Body intentionally elided — see :func:`run_kepler_solver` for the
    catalog-aligned ``unsupported`` response.
    """
    raise RuntimeError("legacy implementation removed; see run_kepler_solver")

def run_kepler_solver_perf(lines_iter):
    """Removed perf workload — Astropy publishes no Kepler solver."""
    n = int(next(lines_iter).strip())
    for _ in range(n):
        next(lines_iter)
    result = {
        "experiment": "kepler_solver_perf",
        "library": "astropy",
        "count": 0,
        "status": "unsupported",
        "reason": "Astropy does not expose a public Kepler-equation solver.",
        "total_ns": 0,
        "per_op_ns": 0,
        "throughput_ops_s": 0,
        "_sink": 0.0,
    }
    json.dump(result, sys.stdout, indent=None)
    print()
