# lunar_position — Summary

Timestamp: 2026-06-03_20-11-15

### Moon Geocentric Position

| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |
|---------|------------------|------------------|------------------|------------------|-------------------|
| erfa | 1.5914 | 9.8219 | 10.1509 | -0.9658 | -0.0626 |
| siderust | 1538.5547 | 4523.3858 | 4624.9002 | 1607.5559 | -185.0465 |
| siderust | 1538.5547 | 4523.3858 | 4624.9002 | 1607.5559 | -185.0465 |
| siderust | 1538.5547 | 4523.3858 | 4624.9002 | 1607.5559 | -185.0465 |
| siderust | 1538.5547 | 4523.3858 | 4624.9002 | 1607.5559 | -185.0465 |
| siderust | 0.2557 | 1.5112 | 1.5625 | 0.4372 | -0.0881 |
| siderust | 0.0011 | 0.0056 | 0.0058 | -0.0017 | 0.0003 |
| astropy | 1.5914 | 9.8219 | 10.1510 | -0.9661 | -0.0626 |
| astropy | 0.0012 | 0.0056 | 0.0058 | -0.0017 | 0.0003 |
| libnova | 0.2651 | 1.5168 | 1.5677 | 0.4483 | -0.0772 |
| anise | 0.0011 | 0.0056 | 0.0058 | -0.0017 | 0.0003 |

### Feature / Model Parity Matrix

| Experiment | erfa | anise | astropy | erfa | libnova | siderust |
|------------|---|---|---|---|---|---|
| lunar_position | Simplified Meeus Ch.47 (major terms only, ~10' ... | SPK translation MOON_J2000 → EARTH_J2000 (DE440... | Simplified Meeus Ch.47 (same algorithm as ERFA ... | Simplified Meeus Ch.47 (major terms only, ~10' ... | ELP 2000-82B geometric (ln_get_lunar_geo_posn +... | Simplified Meeus Ch.47 (major terms only), cent... |

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
  "ephemeris_source": "JPL Horizons (DE441) for reference; Meeus/ELP 2000/DE440 for candidates",
  "library_notes": {
    "astropy": "The 'astropy' adapter uses public Astropy Time and SkyCoord APIs. Astropy may use ERFA internally, but this adapter no longer calls ERFA/pyerfa kernels directly."
  },
  "models": {
    "jpl_horizons": "JPL Horizons geometric VECTORS (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)",
    "erfa": "Simplified Meeus Ch.47 (major terms only, ~10' accuracy)",
    "siderust": "Simplified Meeus Ch.47 (major terms only), centralized in siderust astro module",
    "astropy": "Simplified Meeus Ch.47 (same algorithm as ERFA adapter)",
    "libnova": "ELP 2000-82B geometric (ln_get_lunar_geo_posn + J2000 obliquity rotation; no nutation/aberration)",
    "anise": "SPK translation MOON_J2000 \u2192 EARTH_J2000 (DE440 ephemeris, geometric state vector)"
  },
  "model_parity_class": "external-reference",
  "accuracy_interpretation": "agreement with JPL Horizons geometric VECTORS reference (no aberration / nutation)",
  "reference_mode": "VECTORS geometric ICRF state (X/Y/Z)",
  "reference_frame": "ICRF",
  "reference_center": "Earth geocenter (500@399)",
  "reference_time_scale": "TT",
  "note": "Public geometric lane \u2014 JPL VECTORS (no aberration, no light-time, no nutation). Ranked as best-available model vs JPL reference: libnova uses ELP 2000-82B geometric, ERFA/Astropy use the simplified Meeus Ch.47 fallback (ERFA's eraMoon98 path is best-available when enabled), Siderust uses its centralised Meeus implementation.",
  "candidate_parity": "analytic",
  "lane": "geometric_vector",
  "default_model_parity_class": "external-reference",
  "horizons_source": "DE441",
  "horizons_cache_key": "55e7abbf48dbbef7f78cc24c",
  "horizons_from_cache": true
}
```
