# inv_nutation — Summary

Timestamp: 2026-06-03_20-11-15

### Feature / Model Parity Matrix

| Experiment | erfa | siderust |
|------------|---|---|
| inv_nutation | Transpose of IAU 2000A nutation matrix (eraNum0... | EquatorialTrueOfDate → EquatorialMeanOfDate via... |

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
    "erfa": "Transpose of IAU 2000A nutation matrix (eraNum06a \u2192 rn^T)",
    "siderust": "EquatorialTrueOfDate \u2192 EquatorialMeanOfDate via frame rotation inverse",
    "astropy": "Unsupported in Astropy adapter: no public high-level isolated inverse-nutation API",
    "libnova": "Approximate inverse via \u0394RA/\u0394Dec subtraction (IAU 1980)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
