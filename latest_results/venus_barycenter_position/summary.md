# venus_barycenter_position — Summary

Timestamp: 2026-06-03_20-11-15

### Venus system barycenter Geocentric Position

| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |
|---------|------------------|------------------|------------------|------------------|-------------------|
| siderust | 0.0719 | 0.0767 | 0.0768 | 0.0723 | -0.0053 |
| siderust | 0.0719 | 0.0767 | 0.0768 | 0.0723 | -0.0053 |
| siderust | 0.0719 | 0.0767 | 0.0768 | 0.0723 | -0.0053 |
| siderust | 0.0719 | 0.0767 | 0.0768 | 0.0723 | -0.0053 |
| siderust | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| astropy | 0.0000 | 0.0000 | 0.0000 | -0.0000 | 0.0000 |
| libnova | 0.0151 | 0.0368 | 0.0380 | -0.0154 | -0.0013 |
| anise | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### Feature / Model Parity Matrix

| Experiment | erfa | anise | astropy | libnova | siderust |
|------------|---|---|---|---|---|
| venus_barycenter_position | ERFA eraPlan94 heliocentric Venus system baryce... | SPK translation VENUS SYSTEM BARYCENTER_J2000 -... | Astropy public solar_system_ephemeris('builtin'... | VSOP87 via ln_get_venus system barycenter_rect_... | VSOP87A heliocentric Venus system barycenter st... |

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
  "ephemeris_source": "JPL Horizons (DE441) for reference; VSOP87/plan94/SPK for candidates",
  "library_notes": {
    "astropy": "The 'astropy' adapter uses public Astropy Time and SkyCoord APIs. Astropy may use ERFA internally, but this adapter no longer calls ERFA/pyerfa kernels directly."
  },
  "models": {
    "jpl_horizons": "JPL Horizons geometric VECTORS of Venus system barycenter (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)",
    "erfa": "ERFA eraPlan94 heliocentric Venus system barycenter analytic state minus eraEpv00 Earth state (geometric, J2000 equatorial)",
    "siderust": "VSOP87A heliocentric Venus system barycenter state shifted to geocenter, then rotated to ICRS (geometric, no aberration)",
    "astropy": "Astropy public solar_system_ephemeris('builtin') + get_body_barycentric('venus system barycenter') - get_body_barycentric('earth') (geometric, J2000 equatorial)",
    "libnova": "VSOP87 via ln_get_venus system barycenter_rect_helio - ln_get_earth_rect_helio (geometric rectangular, no nutation/aberration)",
    "anise": "SPK translation VENUS SYSTEM BARYCENTER_J2000 -> EARTH_J2000 (DE440 ephemeris, geometric state vector)"
  },
  "model_parity_class": "external-reference",
  "accuracy_interpretation": "agreement with JPL Horizons geometric VECTORS reference for Venus system barycenter (no aberration / nutation)",
  "reference_mode": "VECTORS geometric ICRF state (X/Y/Z)",
  "reference_frame": "ICRF",
  "reference_center": "Earth geocenter (500@399)",
  "reference_time_scale": "TT",
  "note": "Public geometric lane for Venus system barycenter \u2014 JPL VECTORS (no aberration, no light-time, no nutation). Ranked as best-available model vs JPL reference: libnova VSOP87 geometric path, ERFA/Astropy use eraPlan94 analytic, ANISE uses DE440 SPK when available.",
  "candidate_parity": "analytic",
  "lane": "geometric_vector",
  "default_model_parity_class": "external-reference",
  "horizons_source": "DE441",
  "horizons_cache_key": "77e0a7886650d9106707df20",
  "horizons_from_cache": true
}
```
