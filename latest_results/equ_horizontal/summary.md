# equ_horizontal — Summary

Timestamp: 2026-06-03_20-11-15

### Equatorial → Horizontal (AltAz)

| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |
|---------|------------------|------------------|------------------|------------------|-------------------|
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| astropy | 0.2894 | 0.5175 | 0.5307 | 0.0549 | -0.1314 |
| libnova | 10.4794 | 13.1245 | 13.1973 | 1.0381 | -4.3005 |

### Feature / Model Parity Matrix

| Experiment | erfa | astropy | libnova | siderust |
|------------|---|---|---|---|
| equ_horizontal | Spherical trig via eraHd2ae / eraAe2hd; GAST vi... | Public SkyCoord TETE→AltAz transform with press... | ln_get_hrz_from_equ / ln_get_equ_from_hrz; conv... | Spherical trig matching ERFA formulas; GAST IAU... |

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
    "erfa": "Spherical trig via eraHd2ae / eraAe2hd; GAST via eraGst06a; no refraction",
    "siderust": "Spherical trig matching ERFA formulas; GAST IAU 2006 via siderust astro path",
    "astropy": "Public SkyCoord TETE\u2192AltAz transform with pressure=0",
    "libnova": "ln_get_hrz_from_equ / ln_get_equ_from_hrz; convention fix: az_erfa = (360 - az_ln + 180) % 360",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "accuracy vs ERFA reference (Astropy high-level AltAz path, no direct ERFA trig call)",
  "note": "Azimuth convention: ERFA 0\u00b0=North CW; libnova 0\u00b0=South. Astropy is measured through public TETE/AltAz transforms with atmospheric refraction disabled.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
