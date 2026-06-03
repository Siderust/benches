# gmst_era — Summary

Timestamp: 2026-06-03_20-11-15

### GMST / ERA (Time Scales)

| Library | GMST p50 (arcsec) | GMST p99 (arcsec) | GMST max (arcsec) | ERA p50 (rad) | ERA max (rad) |
|---------|-------------------|-------------------|-------------------|---------------|---------------|
| siderust | 0.000000 | 0.000000 | 0.000000 | 0.0000000000 | 0.0000000000 |
| siderust | 0.000000 | 0.000000 | 0.000000 | 0.0000000000 | 0.0000000000 |
| siderust | 0.000000 | 0.000000 | 0.000000 | 0.0000000000 | 0.0000000000 |
| siderust | 0.000000 | 0.000000 | 0.000000 | 0.0000000000 | 0.0000000000 |
| astropy | 0.000202 | 0.000252 | 0.000253 | 0.0000000010 | 0.0000000012 |
| libnova | 0.037945 | 0.284093 | 0.285826 | — | — |

### Feature / Model Parity Matrix

| Experiment | erfa | astropy | libnova | siderust |
|------------|---|---|---|---|
| gmst_era | GMST=IAU2006 (eraGmst06), ERA=IAU2000 (eraEra00) | Public Time.sidereal_time and Time.earth_rotati... | GMST=Meeus Formula 11.4, GAST=MST+nutation corr... | GST polynomial (IAU 2006 coefficients), ERA fro... |

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
    "erfa": "GMST=IAU2006 (eraGmst06), ERA=IAU2000 (eraEra00)",
    "siderust": "GST polynomial (IAU 2006 coefficients), ERA from IERS definition",
    "astropy": "Public Time.sidereal_time and Time.earth_rotation_angle APIs",
    "libnova": "GMST=Meeus Formula 11.4, GAST=MST+nutation correction (no ERA)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "agreement with ERFA baseline (libnova uses Meeus, no ERA)",
  "mode": "common_denominator",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
