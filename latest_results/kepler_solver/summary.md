# kepler_solver — Summary

Timestamp: 2026-06-03_20-11-15

### Kepler Solver (M→E→ν)

| Library | E p50 (rad) | E max (rad) | ν p50 (rad) | ν max (rad) | Consistency max (rad) |
|---------|-------------|-------------|-------------|-------------|-----------------------|
| siderust | 0.00e+00 | 8.88e-16 | 0.00e+00 | 8.88e-16 | 8.88e-16 |
| siderust | 0.00e+00 | 8.88e-16 | 0.00e+00 | 8.88e-16 | 8.88e-16 |
| siderust | 0.00e+00 | 8.88e-16 | 0.00e+00 | 8.88e-16 | 8.88e-16 |
| siderust | 0.00e+00 | 8.88e-16 | 0.00e+00 | 8.88e-16 | 8.88e-16 |
| libnova | 0.00e+00 | 8.88e-16 | 0.00e+00 | 1.78e-15 | 1.33e-15 |

### Feature / Model Parity Matrix

| Experiment | erfa | libnova | siderust |
|------------|---|---|---|
| kepler_solver | Newton-Raphson iteration (100 iters, tol 1e-15) | Sinnott bisection via ln_solve_kepler (internal... | solve_keplers_equation (internal algorithm) |

† Measurement below reliability threshold (<10 ns/op or CV >20%); treat as indicative only.


## Alignment Checklist

```json
{
  "units": {
    "angles": "radians (internal), mas for error reporting",
    "distances": "meters",
    "float_type": "f64"
  },
  "time_input": "JD (Julian Date), TT scale for precession/nutation, UT1 for sidereal time",
  "time_scales": "TT for BPN matrix; UT1\u2248TT-69.184s simplified",
  "leap_seconds": "not applicable (JD input, no UTC conversion in this experiment)",
  "earth_orientation": {
    "ut1_minus_utc": "not used (JD(TT) input)",
    "polar_motion_xp_yp": "zero (not applied)",
    "eop_mode": "disabled"
  },
  "geodesy": "not applicable (direction-only experiment)",
  "refraction": "disabled",
  "ephemeris_source": "not applicable (no aberration/parallax)",
  "library_notes": {
    "astropy": "The 'astropy' adapter uses public Astropy Time and SkyCoord APIs. Astropy may use ERFA internally, but this adapter no longer calls ERFA/pyerfa kernels directly."
  },
  "models": {
    "erfa": "Newton-Raphson iteration (100 iters, tol 1e-15)",
    "siderust": "solve_keplers_equation (internal algorithm)",
    "astropy": "Newton-Raphson iteration in Python (100 iters, tol 1e-15)",
    "libnova": "Sinnott bisection via ln_solve_kepler (internal convergence ~1e-6 deg)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-parity",
  "accuracy_interpretation": "accuracy vs ERFA reference (same equation, different solvers)",
  "note": "Kepler's equation M = E - e*sin(E) is solved for E given (M, e). Self-consistency M_reconstructed = E - e*sin(E) is the primary metric. libnova uses a bisection method with lower convergence tolerance.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-parity"
}
```
