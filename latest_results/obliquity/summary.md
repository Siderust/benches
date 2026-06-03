# obliquity — Summary

Timestamp: 2026-06-03_20-11-15

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| obliquity | Pure Rx(±ε₀) rotation using eraObl06(J2000) | EclipticMeanJ2000 ↔ EquatorialMeanJ2000 via Tra... |

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
    "erfa": "Pure Rx(\u00b1\u03b5\u2080) rotation using eraObl06(J2000)",
    "siderust": "EclipticMeanJ2000 \u2194 EquatorialMeanJ2000 via TransformFrame",
    "astropy": "Unsupported in Astropy adapter: no public high-level isolated obliquity component API",
    "libnova": "ln_get_equ_from_ecl / ln_get_ecl_from_equ at J2000 (Meeus obliquity)",
    "anise": "Built-in J2000 \u2194 ECLIPJ2000 obliquity rotation"
  },
  "model_parity_class": "model-parity",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-parity"
}
```
