# equ_ecl — Summary

Timestamp: 2026-06-03_20-11-15

### Equatorial ↔ Ecliptic Transform

| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |
|---------|------------------|------------------|------------------|------------------|-------------------|
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| siderust | 0.0000 | 0.0000 | 0.0000 | -0.0000 | -0.0000 |
| astropy | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.0000 |
| libnova | 0.2748 | 1.5332 | 1.5951 | -0.0661 | -0.0999 |

### Feature / Model Parity Matrix

| Experiment | erfa | astropy | libnova | siderust |
|------------|---|---|---|---|
| equ_ecl | IAU 2006 obliquity-based transform (eraEqec06 /... | Public SkyCoord ICRS→BarycentricMeanEcliptic tr... | ln_get_equ_prec (J2000→date) + ln_get_ecl_from_... | IAU 2006 ecliptic-of-date via precession matrix... |

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
    "erfa": "IAU 2006 obliquity-based transform (eraEqec06 / eraEceq06)",
    "siderust": "IAU 2006 ecliptic-of-date via precession matrix + mean obliquity",
    "astropy": "Public SkyCoord ICRS\u2192BarycentricMeanEcliptic transform",
    "libnova": "ln_get_equ_prec (J2000\u2192date) + ln_get_ecl_from_equ + ln_get_equ_from_ecl + ln_get_equ_prec2 (date\u2192J2000)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "agreement with ERFA baseline (libnova Meeus precession/obliquity differs from IAU 2006 Eqec06)",
  "note": "Astropy is measured through its public BarycentricMeanEcliptic orientation, which matches SOFA's mean ecliptic-of-date rotation for direction-only inputs. Siderust uses an explicit IAU 2006 equatorial/ecliptic-of-date transform path. libnova precesses ICRS/J2000 input to mean equator of date before Meeus ecliptic transform.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
