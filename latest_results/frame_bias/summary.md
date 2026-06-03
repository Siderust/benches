# frame_bias — Summary

Timestamp: 2026-06-03_20-11-15

### Frame Bias (ICRS → Mean J2000)

| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |
|---------|---------------|---------------|---------------|-------------------|--------------|----------------|
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 218.6† | 0.9×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 105.1† | 1.8×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 129.4† | 1.5×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 130.6† | 1.5×† |

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| frame_bias | IAU 2006 frame bias matrix component from eraBp06 | IERS 2003 frame bias via frame rotation provide... |

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
    "erfa": "IAU 2006 frame bias matrix component from eraBp06",
    "siderust": "IERS 2003 frame bias via frame rotation provider (ICRS \u2192 EquatorialMeanJ2000)",
    "astropy": "Unsupported in Astropy adapter: no public high-level isolated frame-bias API",
    "libnova": "Not available (no frame bias concept in libnova)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-parity",
  "accuracy_interpretation": "accuracy vs ERFA reference (IAU frame bias is a fixed rotation)",
  "note": "Frame bias is a small (~17 mas) time-independent rotation between ICRS and mean J2000. Astropy and libnova have no public equivalent route in this adapter \u2014 their results are skipped.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-parity"
}
```
