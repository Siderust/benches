# solar_position — Summary

Timestamp: 2026-06-03_20-11-15

### Sun Geocentric Position

| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |
|---------|------------------|------------------|------------------|------------------|-------------------|
| erfa | 0.0029 | 0.0092 | 0.0093 | -0.0009 | 0.0016 |
| siderust | 0.0699 | 0.0772 | 0.0775 | 0.0713 | -0.0034 |
| siderust | 0.0699 | 0.0772 | 0.0775 | 0.0713 | -0.0034 |
| siderust | 0.0699 | 0.0772 | 0.0775 | 0.0713 | -0.0034 |
| siderust | 0.0699 | 0.0772 | 0.0775 | 0.0713 | -0.0034 |
| siderust | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.0000 |
| astropy | 0.0029 | 0.0092 | 0.0093 | -0.0009 | 0.0016 |
| astropy | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| libnova | 0.0174 | 0.0293 | 0.0297 | -0.0174 | -0.0004 |
| anise | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.0000 |

### Feature / Model Parity Matrix

| Experiment | erfa | anise | astropy | erfa | libnova | siderust |
|------------|---|---|---|---|---|---|
| solar_position | VSOP87 via eraEpv00: heliocentric Earth → geoce... | SPK translation SUN_J2000 → EARTH_J2000 (DE440 ... | Astropy public solar_system_ephemeris('builtin'... | VSOP87 via eraEpv00: heliocentric Earth → geoce... | VSOP87 geometric (ln_get_solar_geo_coords; heli... | Geometric heliocentric-ecliptic center transfor... |

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
  "ephemeris_source": "JPL Horizons (DE441) for reference; VSOP87/SPK for candidates",
  "library_notes": {
    "astropy": "The 'astropy' adapter uses public Astropy Time and SkyCoord APIs. Astropy may use ERFA internally, but this adapter no longer calls ERFA/pyerfa kernels directly."
  },
  "models": {
    "jpl_horizons": "JPL Horizons geometric VECTORS (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)",
    "erfa": "VSOP87 via eraEpv00: heliocentric Earth \u2192 geocentric Sun (negate); BCRS equatorial output",
    "siderust": "Geometric heliocentric-ecliptic center transformed to geocentric ICRS (no aberration)",
    "astropy": "Astropy public solar_system_ephemeris('builtin') + get_body_barycentric('sun'/'earth')",
    "libnova": "VSOP87 geometric (ln_get_solar_geo_coords; heliocentric + geocentric rectangular vectors; no nutation/aberration)",
    "anise": "SPK translation SUN_J2000 \u2192 EARTH_J2000 (DE440 ephemeris, geometric state vector)"
  },
  "model_parity_class": "external-reference",
  "accuracy_interpretation": "agreement with JPL Horizons geometric VECTORS reference (no aberration / nutation)",
  "reference_mode": "VECTORS geometric ICRF state (X/Y/Z)",
  "reference_frame": "ICRF",
  "reference_center": "Earth geocenter (500@399)",
  "reference_time_scale": "TT",
  "note": "Public geometric lane \u2014 JPL VECTORS (no aberration, no light-time, no nutation). Ranked as best-available model vs JPL reference: same observable, different physical models (libnova VSOP87 geometric, siderust DE441/DE440/VSOP87 best-available, ANISE SPK).",
  "candidate_parity": "analytic",
  "lane": "geometric_vector",
  "default_model_parity_class": "external-reference",
  "horizons_source": "DE441",
  "horizons_cache_key": "587d2bb1a061ba2291657304",
  "horizons_from_cache": true
}
```
