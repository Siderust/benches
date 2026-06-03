# precession — Summary

Timestamp: 2026-06-03_20-11-15

### Precession (Mean J2000 → Mean of Date)

| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |
|---------|---------------|---------------|---------------|-------------------|--------------|----------------|
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 426.3† | 0.8×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 309.4† | 1.0×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 206.9† | 1.5×† |
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 209.6† | 1.5×† |

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| precession | IAU 2006 pure precession matrix from eraBp06 → rp | IAU 2006 precession via frame rotation provider... |

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
    "erfa": "IAU 2006 pure precession matrix from eraBp06 \u2192 rp",
    "siderust": "IAU 2006 precession via frame rotation provider (EquatorialMeanJ2000 \u2192 EquatorialMeanOfDate)",
    "astropy": "Unsupported in Astropy adapter: no public high-level pure-precession matrix API",
    "libnova": "Meeus precession (\u03b6,z,\u03b8 Equ 20.3) via ln_get_equ_prec2",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "agreement with ERFA baseline (libnova uses Meeus model)",
  "note": "ERFA and Siderust use IAU 2006 precession paths. The Astropy adapter does not expose the isolated component without direct low-level kernels. libnova uses Meeus precession formulae \u2014 expect arcsec-level differences.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
