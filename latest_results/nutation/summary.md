# nutation — Summary

Timestamp: 2026-06-03_20-11-15

### Nutation (Mean of Date → True of Date)

| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |
|---------|---------------|---------------|---------------|-------------------|--------------|----------------|
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 78399.4† | 0.7×† |
| siderust | 0.01 | 0.03 | 0.03 | 0.00 | 39032.0† | 1.4×† |
| siderust | 0.26 | 1.49 | 1.51 | 0.00 | 3171.8† | 17.4×† |
| siderust | 10492.56 | 15951.24 | 15953.41 | 0.00 | 270.6† | 204.3×† |

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| nutation | IAU 2000A nutation (1365 terms) via eraNum06a | IAU 2006/2000A nutation via frame rotation prov... |

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
    "erfa": "IAU 2000A nutation (1365 terms) via eraNum06a",
    "siderust": "IAU 2006/2000A nutation via frame rotation provider",
    "astropy": "Unsupported in Astropy adapter: no public high-level isolated nutation matrix API",
    "libnova": "IAU 1980 nutation (69 terms) via ln_get_equ_nut / ln_nutation",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "agreement with ERFA baseline (libnova uses the older IAU 1980 model)",
  "note": "ERFA and Siderust use IAU 2006/2000A nutation paths. The Astropy adapter does not expose the isolated component without direct low-level kernels. IAU 1980 (libnova) has 69 terms and will differ by tens of mas.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
