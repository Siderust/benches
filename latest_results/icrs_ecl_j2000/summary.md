# icrs_ecl_j2000 — Summary

Timestamp: 2026-06-03_20-11-15

### ICRS → Ecliptic J2000

| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |
|---------|---------------|---------------|---------------|-------------------|--------------|----------------|
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 7.0† | 1.9×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 15.0† | 0.9×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 11.4† | 1.2×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 9.1† | 1.5×† |

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| icrs_ecl_j2000 | IAU 2006 ecliptic rotation at J2000 epoch via e... | ICRS → EclipticMeanJ2000 via frame rotation (me... |

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
    "erfa": "IAU 2006 ecliptic rotation at J2000 epoch via eraEcm06",
    "siderust": "ICRS \u2192 EclipticMeanJ2000 via frame rotation (mean obliquity at J2000)",
    "astropy": "Unsupported in Astropy adapter: no public high-level J2000 ecliptic matrix API",
    "libnova": "Meeus obliquity (Eq 22.2) applied at J2000 epoch",
    "anise": "J2000 \u2194 ECLIPJ2000 built-in orientation rotation (constant obliquity)"
  },
  "model_parity_class": "model-parity",
  "accuracy_interpretation": "accuracy vs ERFA reference (time-independent obliquity)",
  "note": "Time-independent rotation by the mean obliquity at J2000. All IAU-based libraries should agree to \u00b5as level. libnova uses Meeus obliquity which is close but not identical.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-parity"
}
```
