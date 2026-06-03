"""
JPL Horizons API client with persistent caching — two-lane edition.
====================================================================

Provides two clearly-labelled comparison lanes for ephemeris benchmarks:

* ``geometric_vector`` (default for public IDs):
    EPHEM_TYPE=VECTORS, CENTER=500@399 (Earth geocenter),
    REF_PLANE=FRAME (ICRF), REF_SYSTEM=ICRF, VEC_CORR=NONE,
    OUT_UNITS=AU-D, VEC_TABLE=2, TIME_TYPE=TT.
    RA/Dec are derived from the geometric X/Y/Z vector returned by
    Horizons (no aberration, no light-time, no nutation).

* ``apparent_observer`` (legacy diagnostic lane):
    EPHEM_TYPE=OBSERVER, QUANTITIES='1,20', astrometric RA/Dec.
    Useful as a *diagnostic* against candidate libraries that apply
    aberration/nutation internally, but **not** a fair reference for
    geometric-state implementations.

The two lanes have independent cache keys so they never collide.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AU → km (IAU 2012 exact)
AU_KM = 149597870.700

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
BATCH_SIZE = 200

# Lane identifiers
LANE_GEOMETRIC = "geometric_vector"
LANE_APPARENT = "apparent_observer"
VALID_LANES = (LANE_GEOMETRIC, LANE_APPARENT)
DEFAULT_LANE = LANE_GEOMETRIC

# Horizons body IDs
HORIZONS_BODIES = {
    "solar_position": "10",   # Sun
    "lunar_position": "301",  # Moon
    "mercury_position": "199",
    "venus_position": "299",
    "mars_position": "499",
    "jupiter_position": "599",
    "saturn_position": "699",
    "uranus_position": "799",
    "neptune_position": "899",
    "mercury_barycenter_position": "1",
    "venus_barycenter_position": "2",
    "mars_barycenter_position": "4",
    "jupiter_barycenter_position": "5",
    "saturn_barycenter_position": "6",
    "uranus_barycenter_position": "7",
    "neptune_barycenter_position": "8",
}

# Experiments where dist_km is also reported (Moon distance is conventionally km)
DIST_KM_EXPERIMENTS = {"lunar_position"}

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "horizons"


# ---------------------------------------------------------------------------
# Cache key / I/O
# ---------------------------------------------------------------------------

def _normalise_lane(lane: str | None) -> str:
    if lane is None:
        return DEFAULT_LANE
    if lane not in VALID_LANES:
        raise ValueError(
            f"Unknown Horizons lane '{lane}'. Expected one of {VALID_LANES}."
        )
    return lane


def _strip_apparent_suffix(experiment: str) -> str:
    """Map ``*_position_apparent`` IDs back to their base body experiment ID."""
    if experiment.endswith("_apparent"):
        return experiment[: -len("_apparent")]
    return experiment


def _cache_key(
    experiment: str,
    body_id: str,
    epochs_sorted: list[float],
    lane: str | None = None,
) -> str:
    """Compute a deterministic cache key from experiment config + ordered epochs.

    ``lane`` is included in the key so geometric and apparent caches never collide.
    For backward compatibility, when ``lane`` is ``None`` the key uses the legacy
    (lane-less) encoding so existing apparent-style caches keep matching.
    """
    payload_obj: dict = {
        "experiment": experiment,
        "body_id": body_id,
        "epochs": [f"{e:.15f}" for e in epochs_sorted],
    }
    if lane is not None:
        payload_obj["lane"] = lane
    payload = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def _load_cache(cache_key: str) -> dict | None:
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save_cache(cache_key: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_key)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Query parameter builders
# ---------------------------------------------------------------------------

def _build_apparent_query_params(body_id: str, epoch_batch: list[float]) -> dict:
    """OBSERVER / astrometric RA-Dec query (legacy apparent lane)."""
    tlist = "\n".join(f"{e:.15f}" for e in epoch_batch)
    return {
        "format": "text",
        "COMMAND": f"'{body_id}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'500@399'",
        "TIME_TYPE": "TT",
        "TLIST_TYPE": "JD",
        "TLIST": tlist,
        "REF_SYSTEM": "ICRF",
        "QUANTITIES": "'1,20'",
        "ANG_FORMAT": "DEG",
        "EXTRA_PREC": "YES",
        "CSV_FORMAT": "YES",
    }


def _build_geometric_query_params(body_id: str, epoch_batch: list[float]) -> dict:
    """VECTORS query: geometric ICRF state vector, Earth-geocenter, TT, no corrections."""
    tlist = "\n".join(f"{e:.15f}" for e in epoch_batch)
    return {
        "format": "text",
        "COMMAND": f"'{body_id}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": "'500@399'",
        "REF_PLANE": "FRAME",
        "REF_SYSTEM": "ICRF",
        "VEC_CORR": "NONE",
        "OUT_UNITS": "AU-D",
        "VEC_TABLE": "2",
        "VEC_LABELS": "NO",
        "TIME_TYPE": "TT",
        "TLIST_TYPE": "JD",
        "TLIST": tlist,
        "CSV_FORMAT": "YES",
    }


def _build_query_params_legacy_apparent(
    body_id: str,
    epoch_batch: list[float],
) -> dict:
    """Explicit legacy helper: OBSERVER / astrometric query (pre-lane-split default)."""
    return _build_apparent_query_params(body_id, epoch_batch)


def _build_query_params(
    body_id: str,
    epoch_batch: list[float],
    lane: str | None = None,
) -> dict:
    """Build Horizons API query parameters for one batch of epochs.

    When ``lane`` is omitted, :data:`DEFAULT_LANE` (``geometric_vector``) is used.
    Pass :data:`LANE_APPARENT` explicitly for the OBSERVER / astrometric query.
    """
    lane = _normalise_lane(lane)
    if lane == LANE_GEOMETRIC:
        return _build_geometric_query_params(body_id, epoch_batch)
    return _build_apparent_query_params(body_id, epoch_batch)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_source_tag(response_text: str) -> str:
    """Extract the ephemeris source tag(s) from the Horizons response."""
    m = re.search(r"Ephemeris\s*/\s*(DE\d+)", response_text)
    if m:
        return m.group(1)
    m = re.search(r"Target body.*?source\s*:\s*(DE\d+)", response_text, re.IGNORECASE)
    if m:
        return m.group(1)
    tags: list[str] = []
    for tag in re.findall(r"\{source\s*:\s*([A-Za-z0-9_+-]+)\}", response_text, re.IGNORECASE):
        if tag.lower() not in {seen.lower() for seen in tags}:
            tags.append(tag)
    if tags:
        return "+".join(tags)
    return "unknown"


def _parse_csv_block(
    response_text: str,
    expected_epochs: list[float] | None = None,
) -> list[dict]:
    """Parse $$SOE … $$EOE CSV block from a Horizons OBSERVER table.

    Expected CSV columns (QUANTITIES='1,20'):

    * ``JDTT, calendar_date, , RA, DEC, delta, deldot,`` (when JDUT/JDTT column present), or
    * ``calendar_date, , , RA, DEC, delta, deldot,``

    With ``CSV_FORMAT='YES'`` and ``ANG_FORMAT='DEG'`` RA/DEC are decimal degrees and
    delta is in AU.
    """
    soe_match = re.search(r"\$\$SOE\s*\n", response_text)
    eoe_match = re.search(r"\n\$\$EOE", response_text)
    if not soe_match or not eoe_match:
        raise ValueError("Could not find $$SOE/$$EOE markers in Horizons response")

    block = response_text[soe_match.end():eoe_match.start()]
    rows: list[dict] = []
    for row_idx, line in enumerate(block.strip().split("\n")):
        line = line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(",")]
        try:
            if re.match(r"^[+-]?\d+(\.\d+)?$", fields[0]):
                jd_tt = float(fields[0])
            else:
                if expected_epochs is None:
                    raise ValueError(
                        "Horizons CSV row omitted JD and no expected epochs were provided"
                    )
                jd_tt = float(expected_epochs[row_idx])
            ra_deg = float(fields[3])
            dec_deg = float(fields[4])
            delta_au = float(fields[5])
        except (IndexError, ValueError) as exc:
            raise ValueError(
                f"Failed to parse Horizons CSV row: {line!r}"
            ) from exc

        rows.append({
            "jd_tt": jd_tt,
            "ra_deg": ra_deg,
            "dec_deg": dec_deg,
            "delta_au": delta_au,
        })

    if expected_epochs is not None and len(rows) != len(expected_epochs):
        raise ValueError(
            f"Horizons response row count mismatch: expected {len(expected_epochs)}, got {len(rows)}"
        )
    return rows


def _parse_vector_block(
    response_text: str,
    expected_epochs: list[float] | None = None,
) -> list[dict]:
    """Parse $$SOE … $$EOE CSV block from a Horizons VECTORS table.

    With ``VEC_TABLE='2'``, ``VEC_LABELS='NO'`` and ``CSV_FORMAT='YES'`` Horizons
    emits rows of the form::

        JDTT, calendar_date, X, Y, Z, VX, VY, VZ,

    Some response variants omit the JDTT column; in that case ``expected_epochs``
    is used to assign JDTT in order.

    Returns rows with keys ``jd_tt`` and the cartesian geometric vector
    components ``x_au``, ``y_au``, ``z_au`` (in AU, ICRF frame, Earth-centric).
    """
    soe_match = re.search(r"\$\$SOE\s*\n", response_text)
    eoe_match = re.search(r"\n\$\$EOE", response_text)
    if not soe_match or not eoe_match:
        raise ValueError("Could not find $$SOE/$$EOE markers in Horizons response")

    block = response_text[soe_match.end():eoe_match.start()]
    rows: list[dict] = []
    for row_idx, line in enumerate(block.strip().split("\n")):
        line = line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(",")]
        # Drop trailing empty field from a trailing comma if present
        if fields and fields[-1] == "":
            fields = fields[:-1]
        try:
            if re.match(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$", fields[0]):
                jd_tt = float(fields[0])
                # JDTT, calendar_date, X, Y, Z, ...
                x = float(fields[2])
                y = float(fields[3])
                z = float(fields[4])
            else:
                if expected_epochs is None:
                    raise ValueError(
                        "Horizons VECTORS row omitted JD and no expected epochs were provided"
                    )
                jd_tt = float(expected_epochs[row_idx])
                # calendar_date, X, Y, Z, ...
                x = float(fields[1])
                y = float(fields[2])
                z = float(fields[3])
        except (IndexError, ValueError) as exc:
            raise ValueError(
                f"Failed to parse Horizons VECTORS row: {line!r}"
            ) from exc

        rows.append({
            "jd_tt": jd_tt,
            "x_au": x,
            "y_au": y,
            "z_au": z,
        })

    if expected_epochs is not None and len(rows) != len(expected_epochs):
        raise ValueError(
            f"Horizons VECTORS row count mismatch: expected {len(expected_epochs)}, got {len(rows)}"
        )
    return rows


# ---------------------------------------------------------------------------
# Network fetch
# ---------------------------------------------------------------------------

def _http_post(params: dict) -> str:
    encoded = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        HORIZONS_URL,
        data=encoded.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"Horizons API request failed: {exc}") from exc


def _fetch_batch(
    body_id: str,
    epoch_batch: list[float],
    lane: str | None = None,
) -> tuple[list[dict], str]:
    """Fetch one batch of epochs from Horizons.

    Returns ``(parsed_rows, source_tag)``. ``parsed_rows`` schema depends on lane:

    * apparent lane: ``ra_deg, dec_deg, delta_au``
    * geometric lane: ``x_au, y_au, z_au``
    """
    effective_lane = _normalise_lane(lane)
    params = (
        _build_geometric_query_params(body_id, epoch_batch)
        if effective_lane == LANE_GEOMETRIC
        else _build_apparent_query_params(body_id, epoch_batch)
    )
    text = _http_post(params)
    source_tag = _parse_source_tag(text)

    if effective_lane == LANE_GEOMETRIC:
        rows = _parse_vector_block(text, epoch_batch)
    else:
        rows = _parse_csv_block(text, epoch_batch)
    return rows, source_tag


# ---------------------------------------------------------------------------
# Reorder + RA/Dec derivation
# ---------------------------------------------------------------------------

def _vector_to_case(row: dict, experiment: str) -> dict:
    """Convert a geometric-vector cached row to a case with ra_rad/dec_rad/dist."""
    x = row["x_au"]
    y = row["y_au"]
    z = row["z_au"]
    dist_au = math.sqrt(x * x + y * y + z * z)
    if dist_au == 0.0:
        ra = 0.0
        dec = 0.0
    else:
        ra = math.atan2(y, x)
        if ra < 0.0:
            ra += 2.0 * math.pi
        dec = math.asin(max(-1.0, min(1.0, z / dist_au)))
    case = {
        "jd_tt": row["jd_tt"],
        "ra_rad": ra,
        "dec_rad": dec,
        "dist_au": dist_au,
        "x_au": x,
        "y_au": y,
        "z_au": z,
    }
    if experiment in DIST_KM_EXPERIMENTS:
        case["dist_km"] = dist_au * AU_KM
    return case


def _apparent_to_case(row: dict, experiment: str) -> dict:
    """Convert an apparent/observer cached row to a case with ra_rad/dec_rad/dist."""
    deg_to_rad = math.pi / 180.0
    case = {
        "jd_tt": row["jd_tt"],
        "ra_rad": row["ra_deg"] * deg_to_rad,
        "dec_rad": row["dec_deg"] * deg_to_rad,
        "dist_au": row["delta_au"],
    }
    if experiment in DIST_KM_EXPERIMENTS:
        case["dist_km"] = row["delta_au"] * AU_KM
    return case


def _row_is_vector(row: dict) -> bool:
    return "x_au" in row and "y_au" in row and "z_au" in row


def _reorder_cases(rows: list[dict], epoch_list: list[float], experiment: str) -> list[dict]:
    """Reorder fetched rows to match the original epoch list, handling duplicates.

    Detects per-row whether the underlying record is a geometric vector or an
    apparent RA/Dec row and converts accordingly. This keeps the public helper
    backward compatible with legacy apparent caches.
    """
    base_experiment = _strip_apparent_suffix(experiment)
    lookup: dict[str, dict] = {}
    for row in rows:
        jd_key = f"{row['jd_tt']:.10f}"
        lookup[jd_key] = row

    cases: list[dict] = []
    for epoch in epoch_list:
        jd_key = f"{epoch:.10f}"
        row = lookup.get(jd_key)
        if row is None:
            # Try nearest match (within 1e-6 day = 0.086 seconds)
            best = None
            best_dist = 1e-6
            for r in rows:
                d = abs(r["jd_tt"] - epoch)
                if d < best_dist:
                    best_dist = d
                    best = r
            row = best

        if row is None:
            raise RuntimeError(
                f"Horizons response missing epoch JD {epoch:.15f} for {experiment}"
            )

        record = dict(row)
        record["jd_tt"] = epoch
        if _row_is_vector(record):
            cases.append(_vector_to_case(record, base_experiment))
        else:
            cases.append(_apparent_to_case(record, base_experiment))
    return cases


# ---------------------------------------------------------------------------
# Public fetch entry point
# ---------------------------------------------------------------------------

def fetch_horizons_reference(
    experiment: str,
    epochs,
    use_cache: bool = True,
    allow_network: bool = True,
    lane: str | None = None,
) -> dict:
    """Fetch reference positions from JPL Horizons for the given experiment and epochs.

    Args:
        experiment: experiment ID. ``*_position`` for the canonical body, or
            ``*_position_apparent`` to force the apparent lane regardless of
            the ``lane`` argument.
        epochs: array-like of JD(TT) values.
        use_cache: if True, use persistent cache.
        allow_network: if False, require a cache hit and do not contact Horizons.
        lane: ``"geometric_vector"`` (default) or ``"apparent_observer"``.

    Returns:
        dict with keys:

        * ``cases`` — list of dicts with ``jd_tt``, ``ra_rad``, ``dec_rad``,
          ``dist_au`` (plus ``x_au``/``y_au``/``z_au`` on the geometric lane,
          plus ``dist_km`` for lunar_position).
        * ``source_tag`` — e.g. ``"DE441"``.
        * ``cache_key`` — deterministic cache key.
        * ``from_cache`` — bool.
        * ``query_params`` — representative query parameters.
        * ``fetch_timestamp`` — ISO 8601 string or None.
        * ``lane`` — the lane that was used.

    Raises:
        RuntimeError: on fetch failure (cache miss + network error).
        KeyError: on unknown experiment.
    """
    # An explicit *_apparent experiment ID always forces the apparent lane.
    effective_experiment = _strip_apparent_suffix(experiment)
    if experiment.endswith("_apparent"):
        effective_lane = LANE_APPARENT
    else:
        effective_lane = _normalise_lane(lane)

    body_id = HORIZONS_BODIES.get(effective_experiment)
    if body_id is None:
        raise KeyError(f"No Horizons body mapping for experiment '{experiment}'")

    epoch_list = [float(e) for e in epochs]
    sorted_for_key = sorted(set(epoch_list))
    key = _cache_key(effective_experiment, body_id, sorted_for_key, lane=effective_lane)

    # Try cache
    if use_cache:
        cached = _load_cache(key)
        if cached is not None:
            cases = _reorder_cases(cached["rows"], epoch_list, effective_experiment)
            return {
                "cases": cases,
                "source_tag": cached.get("source_tag", "unknown"),
                "cache_key": key,
                "from_cache": True,
                "query_params": cached.get("query_params", {}),
                "fetch_timestamp": cached.get("fetch_timestamp"),
                "lane": cached.get("lane", effective_lane),
            }

    if not allow_network:
        raise RuntimeError(
            f"Horizons cache miss for {experiment} (lane={effective_lane}) "
            "and network access is disabled"
        )

    # Fetch from Horizons in batches (unique epochs only)
    unique_epochs = sorted(set(epoch_list))
    all_rows: list[dict] = []
    source_tags: set[str] = set()

    for i in range(0, len(unique_epochs), BATCH_SIZE):
        batch = unique_epochs[i:i + BATCH_SIZE]
        rows, tag = _fetch_batch(body_id, batch, lane=effective_lane)
        all_rows.extend(rows)
        if tag and tag != "unknown":
            source_tags.add(tag)

    source_tag = ", ".join(sorted(source_tags)) if source_tags else "unknown"

    representative_params = (
        _build_geometric_query_params(body_id, unique_epochs[:5])
        if effective_lane == LANE_GEOMETRIC
        else _build_apparent_query_params(body_id, unique_epochs[:5])
    )
    cache_payload = {
        "experiment": effective_experiment,
        "body_id": body_id,
        "lane": effective_lane,
        "source_tag": source_tag,
        "query_params": representative_params,
        "epochs_count": len(unique_epochs),
        "rows": all_rows,
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save_cache(key, cache_payload)

    cases = _reorder_cases(all_rows, epoch_list, effective_experiment)
    return {
        "cases": cases,
        "source_tag": source_tag,
        "cache_key": key,
        "from_cache": False,
        "query_params": representative_params,
        "fetch_timestamp": cache_payload["fetch_timestamp"],
        "lane": effective_lane,
    }
