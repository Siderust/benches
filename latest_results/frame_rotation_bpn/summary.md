# frame_rotation_bpn — Summary

Timestamp: 2026-06-03_20-11-15

### Frame Rotation (BPN: ICRS → True-of-Date)

| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Matrix Frob p50 | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |
|---------|---------------|---------------|---------------|-----------------|-------------------|--------------|----------------|
| siderust | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 40362.7† | 2.2×† |
| siderust | 0.01 | 0.02 | 0.02 | 0.00 | 0.00 | 63206.7† | 1.4×† |
| siderust | 0.33 | 1.07 | 1.10 | 0.00 | 0.00 | 3974.2† | 22.7×† |
| siderust | 9651.15 | 14714.97 | 14783.51 | 0.00 | 0.00 | 212.7† | 424.0×† |
| astropy | 0.00 | 0.00 | 0.00 | — | 0.00 | 1628094.6† | 0.1×† |
| libnova | 39.46 | 822.59 | 875.90 | — | 0.00 | 2966.3† | 30.4×† |

### Feature / Model Parity Matrix

| Experiment | erfa | astropy | libnova | siderust |
|------------|---|---|---|---|
| frame_rotation_bpn | IAU 2006/2000A bias-precession-nutation (eraPnm... | Public SkyCoord GCRS→TETE transform (equinox-ba... | Meeus precession (ζ,z,θ Equ 20.3) + IAU 1980 nu... | IERS 2003 frame bias + IAU 2006 precession + IA... |

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
    "erfa": "IAU 2006/2000A bias-precession-nutation (eraPnm06a)",
    "siderust": "IERS 2003 frame bias + IAU 2006 precession + IAU 2006/2000A nutation (frame_rotation provider)",
    "astropy": "Public SkyCoord GCRS\u2192TETE transform (equinox-based Astropy frame graph)",
    "libnova": "Meeus precession (\u03b6,z,\u03b8 Equ 20.3) + IAU 1980 nutation (63-term Table 21A), applied as RA/Dec corrections (no BPN matrix)",
    "anise": "Not available in ANISE adapter for this experiment"
  },
  "model_parity_class": "model-mismatch",
  "accuracy_interpretation": "agreement with ERFA baseline (Astropy high-level transform, no direct ERFA call in adapter)",
  "mode": "common_denominator",
  "note": "ERFA is the raw SOFA-style BPN matrix reference. Astropy is measured through its public GCRS/TETE transform graph, whose equinox-based orientation matches the SOFA pnm06a BPN matrix for direction-only inputs. Siderust now uses the same IAU 2006/2000A decomposition. libnova uses Meeus precession + IAU 1980 nutation via coordinate-level API (no rotation matrix). Differences measure the model gap, not implementation bugs.",
  "candidate_parity": "model-parity",
  "default_model_parity_class": "model-mismatch"
}
```
