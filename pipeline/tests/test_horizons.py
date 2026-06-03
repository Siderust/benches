"""
Tests for the JPL Horizons two-lane client and external-reference orchestrator path.
====================================================================================

Unit tests use canned text fixtures — no live network requests.

The client now supports two lanes:

* ``geometric_vector`` (default): EPHEM_TYPE=VECTORS, VEC_CORR=NONE, ICRF.
* ``apparent_observer`` (legacy): EPHEM_TYPE=OBSERVER, astrometric RA/Dec.

Cache keys differ across lanes so the two never collide.
"""

import math
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
LAB_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(LAB_ROOT))

from horizons_client import (
    _parse_csv_block,
    _parse_source_tag,
    _parse_vector_block,
    _reorder_cases,
    _cache_key,
    _load_cache,
    _save_cache,
    _build_query_params,
    _build_query_params_legacy_apparent,
    _build_geometric_query_params,
    _build_apparent_query_params,
    fetch_horizons_reference,
    BATCH_SIZE,
    AU_KM,
    HORIZONS_BODIES,
    LANE_APPARENT,
    LANE_GEOMETRIC,
)


# ---------------------------------------------------------------------------
# Canned Horizons response fixtures
# ---------------------------------------------------------------------------

SAMPLE_HORIZONS_RESPONSE = """\
*******************************************************************************
JPL/HORIZONS                      Sun (10)              2026-Mar-11 00:00:00
Rec #:10      Soln.date: 2025-Jan-01_00:00:00   # obs: 9999 (all types)

*******************************************************************************
Ephemeris / PORT_LOGIN Tue Mar 11 00:00:00 2026 Jpl/Horizons
Target body name: Sun (10)                    {source: DE441}
Center body name: Earth (399)                 {source: DE441}
*******************************************************************************
$$SOE
2451545.000000000, 2000-Jan-01 12:00:00.0000,  ,281.28783929, -23.01394503,  0.983320046, -0.0001234,
2460310.500000000, 2024-Jan-01 00:00:00.0000,  ,280.87654321, -22.98765432,  0.983412345,  0.0000567,
2451625.000000000, 2000-Mar-20 12:00:00.0000,  ,359.94567890,  -0.01234567,  0.995678901,  0.0002345,
$$EOE
*******************************************************************************
"""

SAMPLE_MOON_RESPONSE = """\
*******************************************************************************
Ephemeris / PORT_LOGIN Tue Mar 11 00:00:00 2026 Jpl/Horizons
Target body name: Moon (301)                  {source: DE441}
Center body name: Earth (399)                 {source: DE441}
*******************************************************************************
$$SOE
2451545.000000000, 2000-Jan-01 12:00:00.0000,  ,123.45678900, -5.67890123,  0.002710000,  0.0001234,
2460310.500000000, 2024-Jan-01 00:00:00.0000,  ,234.56789012,  12.34567890,  0.002650000, -0.0000567,
$$EOE
*******************************************************************************
"""

SAMPLE_MARS_RESPONSE = """\
*******************************************************************************
Ephemeris / API_USER Thu Mar 12 16:02:38 2026 Pasadena, USA      / Horizons
Target body name: Mars (499)                      {source: mar099}
Center body name: Earth (399)                     {source: DE441}
*******************************************************************************
$$SOE
 1987-Oct-12 08:24:50.515, , , 182.642373589,  -0.065640629,  2.59333643461701, -5.7254651,
 2000-Jan-01 12:00:00.000, , , 330.524049117, -13.180707612,  1.84968383439833,  9.3886287,
$$EOE
*******************************************************************************
"""

# Geometric VECTORS fixture. With VEC_TABLE=2, VEC_LABELS=NO, CSV_FORMAT=YES
# Horizons emits: JDTT, calendar_date, X, Y, Z, VX, VY, VZ,
#
# The Sun row below is an Earth-geocentric ICRF vector at J2000. The Sun is
# roughly at (X≈0.18 AU, Y≈-0.89 AU, Z≈-0.39 AU) seen from Earth at that epoch.
SAMPLE_GEOMETRIC_SUN_RESPONSE = """\
*******************************************************************************
Ephemeris / API_USER Tue Mar 11 00:00:00 2026 Pasadena, USA      / Horizons
Target body name: Sun (10)                       {source: DE441}
Center body name: Earth (399)                    {source: DE441}
Output units    : AU-D
Reference frame : Ecliptic and Mean Equinox of Reference Epoch
Reference plane : FRAME
*******************************************************************************
$$SOE
2451545.000000000, A.D. 2000-Jan-01 12:00:00.0000,  1.771068499773438E-01, -8.929638091215927E-01, -3.872079112647570E-01,  0.0, 0.0, 0.0,
2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000,  1.685120000000000E-01, -8.910000000000000E-01, -3.862000000000000E-01,  0.0, 0.0, 0.0,
$$EOE
*******************************************************************************
"""

SAMPLE_GEOMETRIC_NO_JD_RESPONSE = """\
*******************************************************************************
Ephemeris / API_USER Tue Mar 11 00:00:00 2026 Pasadena, USA      / Horizons
Target body name: Mars (499)                     {source: DE441}
*******************************************************************************
$$SOE
 A.D. 2000-Jan-01 12:00:00.0000, -1.000000000000000E+00,  0.000000000000000E+00,  0.000000000000000E+00,  0.0, 0.0, 0.0,
$$EOE
*******************************************************************************
"""


# ---------------------------------------------------------------------------
# Source tag parsing (unchanged)
# ---------------------------------------------------------------------------

class TestParseSourceTag:
    def test_parses_de441(self):
        assert _parse_source_tag(SAMPLE_HORIZONS_RESPONSE) == "DE441"

    def test_fallback_unknown(self):
        assert _parse_source_tag("no ephemeris info here") == "unknown"

    def test_parses_de440(self):
        text = "Ephemeris / DE440\nsome other content"
        assert _parse_source_tag(text) == "DE440"

    def test_parses_combined_planetary_source_tags(self):
        assert _parse_source_tag(SAMPLE_MARS_RESPONSE) == "mar099+DE441"

    def test_geometric_response_keeps_source_tag(self):
        assert _parse_source_tag(SAMPLE_GEOMETRIC_SUN_RESPONSE) == "DE441"


# ---------------------------------------------------------------------------
# Apparent (OBSERVER) CSV parsing
# ---------------------------------------------------------------------------

class TestParseCsvBlock:
    def test_parses_sun_response(self):
        rows = _parse_csv_block(SAMPLE_HORIZONS_RESPONSE)
        assert len(rows) == 3
        assert rows[0]["jd_tt"] == 2451545.0
        assert abs(rows[0]["ra_deg"] - 281.28783929) < 1e-8
        assert abs(rows[0]["dec_deg"] - (-23.01394503)) < 1e-8
        assert abs(rows[0]["delta_au"] - 0.983320046) < 1e-9

    def test_parses_moon_response(self):
        rows = _parse_csv_block(SAMPLE_MOON_RESPONSE)
        assert len(rows) == 2
        assert rows[0]["jd_tt"] == 2451545.0
        assert abs(rows[0]["ra_deg"] - 123.456789) < 1e-6
        assert abs(rows[1]["dec_deg"] - 12.3456789) < 1e-6

    def test_missing_soe_raises(self):
        with pytest.raises(ValueError, match="SOE"):
            _parse_csv_block("no markers here")

    def test_parses_calendar_only_rows_when_epochs_are_known(self):
        epochs = [2447080.850584669, 2451545.0]
        rows = _parse_csv_block(SAMPLE_MARS_RESPONSE, epochs)
        assert len(rows) == 2
        assert rows[0]["jd_tt"] == epochs[0]
        assert abs(rows[0]["ra_deg"] - 182.642373589) < 1e-9
        assert abs(rows[1]["delta_au"] - 1.84968383439833) < 1e-12


# ---------------------------------------------------------------------------
# Geometric VECTORS parsing
# ---------------------------------------------------------------------------

class TestParseVectorBlock:
    def test_parses_sun_vector_response(self):
        rows = _parse_vector_block(SAMPLE_GEOMETRIC_SUN_RESPONSE)
        assert len(rows) == 2
        assert rows[0]["jd_tt"] == 2451545.0
        assert abs(rows[0]["x_au"] - 0.1771068499773438) < 1e-12
        assert abs(rows[0]["y_au"] - -0.8929638091215927) < 1e-12
        assert abs(rows[0]["z_au"] - -0.3872079112647570) < 1e-12

    def test_parses_rows_without_jd_using_expected_epochs(self):
        rows = _parse_vector_block(SAMPLE_GEOMETRIC_NO_JD_RESPONSE, [2451545.0])
        assert len(rows) == 1
        assert rows[0]["jd_tt"] == 2451545.0
        assert abs(rows[0]["x_au"] - -1.0) < 1e-12
        assert rows[0]["y_au"] == 0.0
        assert rows[0]["z_au"] == 0.0

    def test_missing_soe_raises(self):
        with pytest.raises(ValueError, match="SOE"):
            _parse_vector_block("no markers")

    def test_row_count_mismatch_raises(self):
        with pytest.raises(ValueError, match="row count mismatch"):
            _parse_vector_block(SAMPLE_GEOMETRIC_SUN_RESPONSE, [2451545.0])


# ---------------------------------------------------------------------------
# Reordering: handles both schemas
# ---------------------------------------------------------------------------

class TestReorderCases:
    def test_apparent_preserves_original_order(self):
        rows = [
            {"jd_tt": 100.0, "ra_deg": 10.0, "dec_deg": 20.0, "delta_au": 1.0},
            {"jd_tt": 200.0, "ra_deg": 30.0, "dec_deg": 40.0, "delta_au": 2.0},
        ]
        cases = _reorder_cases(rows, [200.0, 100.0], "solar_position")
        assert len(cases) == 2
        assert cases[0]["jd_tt"] == 200.0
        assert cases[1]["jd_tt"] == 100.0

    def test_apparent_converts_to_radians(self):
        rows = [{"jd_tt": 100.0, "ra_deg": 180.0, "dec_deg": 90.0, "delta_au": 1.0}]
        cases = _reorder_cases(rows, [100.0], "solar_position")
        assert abs(cases[0]["ra_rad"] - math.pi) < 1e-10
        assert abs(cases[0]["dec_rad"] - math.pi / 2) < 1e-10

    def test_lunar_apparent_includes_dist_km(self):
        rows = [{"jd_tt": 100.0, "ra_deg": 10.0, "dec_deg": 20.0, "delta_au": 0.00257}]
        cases = _reorder_cases(rows, [100.0], "lunar_position")
        assert "dist_km" in cases[0]
        assert abs(cases[0]["dist_km"] - 0.00257 * AU_KM) < 1.0

    def test_planet_apparent_keeps_dist_au_only(self):
        rows = [{"jd_tt": 100.0, "ra_deg": 10.0, "dec_deg": 20.0, "delta_au": 1.523}]
        cases = _reorder_cases(rows, [100.0], "mars_position")
        assert "dist_km" not in cases[0]
        assert abs(cases[0]["dist_au"] - 1.523) < 1e-12

    def test_geometric_vector_derives_ra_dec(self):
        # Vector pointing along +X (ra=0, dec=0)
        rows = [{"jd_tt": 100.0, "x_au": 1.0, "y_au": 0.0, "z_au": 0.0}]
        cases = _reorder_cases(rows, [100.0], "mars_position")
        assert abs(cases[0]["ra_rad"]) < 1e-12
        assert abs(cases[0]["dec_rad"]) < 1e-12
        assert abs(cases[0]["dist_au"] - 1.0) < 1e-12
        assert cases[0]["x_au"] == 1.0

    def test_geometric_vector_handles_negative_y(self):
        # Vector at (1, -1, 0): ra ~ 315 deg, dec ~ 0
        rows = [{"jd_tt": 100.0, "x_au": 1.0, "y_au": -1.0, "z_au": 0.0}]
        cases = _reorder_cases(rows, [100.0], "solar_position")
        # atan2(-1, 1) = -pi/4, wrapped to 7pi/4
        assert abs(cases[0]["ra_rad"] - (7.0 * math.pi / 4.0)) < 1e-10
        assert abs(cases[0]["dec_rad"]) < 1e-12

    def test_geometric_lunar_includes_dist_km(self):
        rows = [{"jd_tt": 100.0, "x_au": 0.00257, "y_au": 0.0, "z_au": 0.0}]
        cases = _reorder_cases(rows, [100.0], "lunar_position")
        assert "dist_km" in cases[0]
        assert abs(cases[0]["dist_km"] - 0.00257 * AU_KM) < 1.0

    def test_apparent_suffix_strips_to_base_for_distance_handling(self):
        rows = [{"jd_tt": 100.0, "ra_deg": 0.0, "dec_deg": 0.0, "delta_au": 0.00257}]
        cases = _reorder_cases(rows, [100.0], "lunar_position_apparent")
        assert "dist_km" in cases[0]


# ---------------------------------------------------------------------------
# Query parameter builders
# ---------------------------------------------------------------------------

class TestQueryParams:
    def test_planet_body_ids_are_mapped(self):
        assert HORIZONS_BODIES["mercury_position"] == "199"
        assert HORIZONS_BODIES["venus_position"] == "299"
        assert HORIZONS_BODIES["mars_position"] == "499"
        assert HORIZONS_BODIES["jupiter_position"] == "599"
        assert HORIZONS_BODIES["saturn_position"] == "699"
        assert HORIZONS_BODIES["uranus_position"] == "799"
        assert HORIZONS_BODIES["neptune_position"] == "899"

    def test_planet_barycenter_body_ids_are_distinct(self):
        assert HORIZONS_BODIES["mercury_barycenter_position"] == "1"
        assert HORIZONS_BODIES["venus_barycenter_position"] == "2"
        assert HORIZONS_BODIES["mars_barycenter_position"] == "4"
        assert HORIZONS_BODIES["jupiter_barycenter_position"] == "5"
        assert HORIZONS_BODIES["saturn_barycenter_position"] == "6"
        assert HORIZONS_BODIES["uranus_barycenter_position"] == "7"
        assert HORIZONS_BODIES["neptune_barycenter_position"] == "8"

    def test_geometric_default_when_lane_omitted(self):
        params = _build_query_params("10", [2451545.0, 2460310.5])
        assert params["EPHEM_TYPE"] == "VECTORS"
        assert params["VEC_CORR"] == "NONE"
        assert "QUANTITIES" not in params

    def test_legacy_apparent_helper(self):
        params = _build_query_params_legacy_apparent("10", [2451545.0, 2460310.5])
        assert params["EPHEM_TYPE"] == "OBSERVER"
        assert params["COMMAND"] == "'10'"
        assert params["CENTER"] == "'500@399'"
        assert params["QUANTITIES"] == "'1,20'"
        assert params["ANG_FORMAT"] == "DEG"
        assert params["CSV_FORMAT"] == "YES"

    def test_apparent_explicit_lane(self):
        params = _build_query_params("10", [2451545.0], lane=LANE_APPARENT)
        assert params["EPHEM_TYPE"] == "OBSERVER"

    def test_geometric_lane_uses_vectors(self):
        params = _build_query_params("10", [2451545.0, 2460310.5], lane=LANE_GEOMETRIC)
        assert params["EPHEM_TYPE"] == "VECTORS"
        assert params["CENTER"] == "'500@399'"
        assert params["REF_PLANE"] == "FRAME"
        assert params["REF_SYSTEM"] == "ICRF"
        assert params["VEC_CORR"] == "NONE"
        assert params["OUT_UNITS"] == "AU-D"
        assert params["VEC_TABLE"] == "2"
        assert params["VEC_LABELS"] == "NO"
        assert params["TIME_TYPE"] == "TT"
        assert params["TLIST_TYPE"] == "JD"
        assert params["CSV_FORMAT"] == "YES"
        # Quantities/Ang_format must not leak into a vector query
        assert "QUANTITIES" not in params
        assert "ANG_FORMAT" not in params

    def test_geometric_builder_directly(self):
        params = _build_geometric_query_params("499", [2451545.0])
        assert params["EPHEM_TYPE"] == "VECTORS"
        assert params["VEC_CORR"] == "NONE"

    def test_apparent_builder_directly(self):
        params = _build_apparent_query_params("499", [2451545.0])
        assert params["EPHEM_TYPE"] == "OBSERVER"

    def test_tlist_contains_epochs(self):
        params = _build_geometric_query_params("10", [2451545.0, 2460310.5])
        assert "2451545" in params["TLIST"]
        assert "2460310" in params["TLIST"]

    def test_batch_size_constant(self):
        assert BATCH_SIZE == 200


# ---------------------------------------------------------------------------
# Cache key behaviour — lane separation is the headline guarantee
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_deterministic_within_a_lane(self):
        k1 = _cache_key("solar_position", "10", [2451545.0, 2460310.5], lane=LANE_GEOMETRIC)
        k2 = _cache_key("solar_position", "10", [2451545.0, 2460310.5], lane=LANE_GEOMETRIC)
        assert k1 == k2

    def test_differs_for_different_epochs(self):
        k1 = _cache_key("solar_position", "10", [2451545.0], lane=LANE_GEOMETRIC)
        k2 = _cache_key("solar_position", "10", [2460310.5], lane=LANE_GEOMETRIC)
        assert k1 != k2

    def test_differs_for_different_experiments(self):
        k1 = _cache_key("solar_position", "10", [2451545.0], lane=LANE_GEOMETRIC)
        k2 = _cache_key("lunar_position", "301", [2451545.0], lane=LANE_GEOMETRIC)
        assert k1 != k2

    def test_geometric_and_apparent_keys_never_collide(self):
        epochs = [2451545.0, 2460310.5, 2451625.0]
        geo = _cache_key("solar_position", "10", epochs, lane=LANE_GEOMETRIC)
        app = _cache_key("solar_position", "10", epochs, lane=LANE_APPARENT)
        assert geo != app

    def test_lane_none_matches_legacy_apparent_encoding(self):
        """Legacy caches (written before the lane field existed) must keep matching
        when callers don't pass ``lane`` — this preserves on-disk data."""
        epochs = [2451545.0]
        legacy = _cache_key("solar_position", "10", epochs)
        # The lane-less encoding stays as-is; lane-tagged keys differ
        assert legacy != _cache_key("solar_position", "10", epochs, lane=LANE_APPARENT)
        assert legacy != _cache_key("solar_position", "10", epochs, lane=LANE_GEOMETRIC)


class TestCacheIO:
    def test_cache_round_trip(self, tmp_path):
        with patch("horizons_client.CACHE_DIR", tmp_path):
            data = {"test": "value", "rows": [{"jd_tt": 1.0}]}
            _save_cache("test_key_abc", data)
            assert _load_cache("test_key_abc") == data

    def test_cache_miss_returns_none(self, tmp_path):
        with patch("horizons_client.CACHE_DIR", tmp_path):
            assert _load_cache("nonexistent_key") is None


# ---------------------------------------------------------------------------
# fetch_horizons_reference — end to end with mocked network
# ---------------------------------------------------------------------------

class TestFetchHorizonsReference:
    def _geometric_cached(self):
        return {
            "experiment": "solar_position",
            "body_id": "10",
            "lane": LANE_GEOMETRIC,
            "source_tag": "DE441",
            "query_params": {},
            "epochs_count": 1,
            "rows": [{"jd_tt": 2451545.0, "x_au": 1.0, "y_au": 0.0, "z_au": 0.0}],
            "fetch_timestamp": "2026-01-01T00:00:00Z",
        }

    def _apparent_cached(self):
        return {
            "experiment": "solar_position",
            "body_id": "10",
            "lane": LANE_APPARENT,
            "source_tag": "DE441",
            "query_params": {},
            "epochs_count": 1,
            "rows": [{"jd_tt": 2451545.0, "ra_deg": 280.0, "dec_deg": -23.0, "delta_au": 0.98}],
            "fetch_timestamp": "2026-01-01T00:00:00Z",
        }

    def test_geometric_default_cache_hit_skips_network(self, tmp_path):
        cached = self._geometric_cached()
        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch") as mock_fetch:
            key = _cache_key("solar_position", "10", [2451545.0], lane=LANE_GEOMETRIC)
            _save_cache(key, cached)
            result = fetch_horizons_reference("solar_position", [2451545.0], use_cache=True)

            mock_fetch.assert_not_called()
            assert result["from_cache"] is True
            assert result["lane"] == LANE_GEOMETRIC
            assert result["source_tag"] == "DE441"
            # Derived RA/Dec from vector (1, 0, 0)
            assert abs(result["cases"][0]["ra_rad"]) < 1e-12
            assert abs(result["cases"][0]["dec_rad"]) < 1e-12
            assert abs(result["cases"][0]["dist_au"] - 1.0) < 1e-12

    def test_apparent_lane_cache_hit(self, tmp_path):
        cached = self._apparent_cached()
        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch") as mock_fetch:
            key = _cache_key("solar_position", "10", [2451545.0], lane=LANE_APPARENT)
            _save_cache(key, cached)
            result = fetch_horizons_reference(
                "solar_position", [2451545.0], use_cache=True, lane=LANE_APPARENT,
            )
            mock_fetch.assert_not_called()
            assert result["lane"] == LANE_APPARENT
            assert abs(result["cases"][0]["ra_rad"] - 280.0 * math.pi / 180.0) < 1e-10

    def test_apparent_suffix_forces_apparent_lane(self, tmp_path):
        """Calling fetch with ``solar_position_apparent`` must force lane=apparent."""
        cached = self._apparent_cached()
        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch") as mock_fetch:
            key = _cache_key("solar_position", "10", [2451545.0], lane=LANE_APPARENT)
            _save_cache(key, cached)
            # No explicit lane, but the _apparent suffix overrides the default
            result = fetch_horizons_reference(
                "solar_position_apparent", [2451545.0], use_cache=True,
            )
            mock_fetch.assert_not_called()
            assert result["lane"] == LANE_APPARENT

    def test_geometric_cache_miss_fetches_with_vector_params(self, tmp_path):
        mock_rows = [{"jd_tt": 2451545.0, "x_au": 0.5, "y_au": 0.5, "z_au": 0.0}]

        captured = {}
        def fake_fetch(body_id, batch, lane=None):
            captured["body_id"] = body_id
            captured["lane"] = lane
            return mock_rows, "DE441"

        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch", side_effect=fake_fetch):
            result = fetch_horizons_reference("solar_position", [2451545.0])

        assert captured["lane"] == LANE_GEOMETRIC
        assert captured["body_id"] == "10"
        assert result["from_cache"] is False
        assert result["source_tag"] == "DE441"
        assert result["lane"] == LANE_GEOMETRIC
        # Cache payload now exists under the geometric key
        key = _cache_key("solar_position", "10", [2451545.0], lane=LANE_GEOMETRIC)
        with patch("horizons_client.CACHE_DIR", tmp_path):
            cached = _load_cache(key)
        assert cached is not None
        assert cached["lane"] == LANE_GEOMETRIC
        assert cached["query_params"]["EPHEM_TYPE"] == "VECTORS"
        assert cached["query_params"]["VEC_CORR"] == "NONE"

    def test_apparent_cache_miss_uses_observer_params(self, tmp_path):
        mock_rows = [{"jd_tt": 2451545.0, "ra_deg": 280.0, "dec_deg": -23.0, "delta_au": 0.98}]

        captured = {}
        def fake_fetch(body_id, batch, lane=None):
            captured["lane"] = lane
            return mock_rows, "DE441"

        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch", side_effect=fake_fetch):
            result = fetch_horizons_reference(
                "solar_position", [2451545.0], lane=LANE_APPARENT,
            )

        assert captured["lane"] == LANE_APPARENT
        assert result["lane"] == LANE_APPARENT
        key = _cache_key("solar_position", "10", [2451545.0], lane=LANE_APPARENT)
        with patch("horizons_client.CACHE_DIR", tmp_path):
            cached = _load_cache(key)
        assert cached is not None
        assert cached["query_params"]["EPHEM_TYPE"] == "OBSERVER"

    def test_fetch_failure_raises_runtime_error(self, tmp_path):
        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch",
                   side_effect=RuntimeError("Connection refused")):
            with pytest.raises(RuntimeError, match="Connection refused"):
                fetch_horizons_reference("solar_position", [2451545.0])

    def test_offline_cache_miss_raises_before_network(self, tmp_path):
        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch") as mock_fetch:
            with pytest.raises(RuntimeError, match="network access is disabled"):
                fetch_horizons_reference(
                    "solar_position", [2451545.0],
                    use_cache=True, allow_network=False,
                )
            mock_fetch.assert_not_called()

    def test_unknown_experiment_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown_experiment"):
            fetch_horizons_reference("unknown_experiment", [2451545.0])

    def test_unknown_lane_raises(self):
        with pytest.raises(ValueError, match="Unknown Horizons lane"):
            fetch_horizons_reference("solar_position", [2451545.0], lane="apparent_geocentric")

    def test_batching_for_large_epoch_sets(self, tmp_path):
        epochs = [2451545.0 + i for i in range(450)]
        mock_rows = [{"jd_tt": e, "x_au": 1.0, "y_au": 0.0, "z_au": 0.0} for e in epochs]

        def batch_fetcher(body_id, batch, lane=None):
            return ([r for r in mock_rows if r["jd_tt"] in batch], "DE441")

        with patch("horizons_client.CACHE_DIR", tmp_path), \
             patch("horizons_client._fetch_batch", side_effect=batch_fetcher) as mock_fetch:
            result = fetch_horizons_reference("solar_position", epochs)

        assert mock_fetch.call_count == 3
        assert len(result["cases"]) == 450


# ---------------------------------------------------------------------------
# Orchestrator external-reference path (integration with mocks)
# ---------------------------------------------------------------------------

class TestExternalReferenceOrchestrator:
    """Test the orchestrator's _run_external_reference_experiment path."""

    @pytest.fixture
    def mock_horizons_solar(self):
        def mock_fetch(experiment, epochs, use_cache=True, allow_network=True, lane=None):
            cases = []
            for e in epochs:
                cases.append({
                    "jd_tt": float(e),
                    "ra_rad": 280.0 * math.pi / 180.0,
                    "dec_rad": -23.0 * math.pi / 180.0,
                    "dist_au": 0.98,
                })
            return {
                "cases": cases,
                "source_tag": "DE441",
                "cache_key": "test_cache_key",
                "from_cache": True,
                "query_params": {},
                "fetch_timestamp": "2026-01-01T00:00:00Z",
                "lane": lane or LANE_GEOMETRIC,
            }
        return mock_fetch

    @pytest.fixture
    def mock_adapter_result(self):
        def _make(n):
            return {
                "cases": [
                    {"jd_tt": 2451545.0 + i, "ra_rad": 4.89, "dec_rad": -0.40, "dist_au": 0.98}
                    for i in range(n)
                ],
                "per_op_ns": 1000.0,
                "total_ns": 1000000.0,
                "count": n,
            }
        return _make

    def test_solar_produces_jpl_horizons_reference(self, mock_horizons_solar, mock_adapter_result):
        import orchestrator as orch
        with patch.object(orch, "fetch_horizons_reference", mock_horizons_solar), \
             patch.object(orch, "run_adapter", return_value=mock_adapter_result(10)), \
             patch.object(orch, "ensure_rust_adapters_built"):
            results = orch.run_experiment_solar_position(n=10, seed=42, run_perf=False)
            assert len(results) > 0
            for r in results:
                assert r["reference_library"] == "jpl_horizons"
                assert r["reference_performance"] == {}

    def test_erfa_appears_as_candidate(self, mock_horizons_solar, mock_adapter_result):
        import orchestrator as orch
        with patch.object(orch, "fetch_horizons_reference", mock_horizons_solar), \
             patch.object(orch, "run_adapter", return_value=mock_adapter_result(10)), \
             patch.object(orch, "ensure_rust_adapters_built"):
            results = orch.run_experiment_solar_position(n=10, seed=42, run_perf=False)
            assert "erfa" in [r["candidate_library"] for r in results]

    def test_horizons_failure_aborts_experiment_cleanly(self):
        def failing_fetch(experiment, epochs, use_cache=True, allow_network=True, lane=None):
            raise RuntimeError("Network unreachable")
        import orchestrator as orch
        with patch.object(orch, "fetch_horizons_reference", failing_fetch), \
             patch.object(orch, "run_adapter"), \
             patch.object(orch, "ensure_rust_adapters_built"):
            results = orch.run_experiment_solar_position(n=10, seed=42, run_perf=False)
            assert results == []

    def test_alignment_shows_horizons_source(self, mock_horizons_solar, mock_adapter_result):
        import orchestrator as orch
        with patch.object(orch, "fetch_horizons_reference", mock_horizons_solar), \
             patch.object(orch, "run_adapter", return_value=mock_adapter_result(10)), \
             patch.object(orch, "ensure_rust_adapters_built"):
            results = orch.run_experiment_solar_position(n=10, seed=42, run_perf=False)
            alignment = results[0]["alignment"]
            assert alignment["horizons_source"] == "DE441"
            assert "horizons_cache_key" in alignment

    def test_planet_produces_jpl_horizons_reference(self, mock_horizons_solar, mock_adapter_result):
        import orchestrator as orch
        with patch.object(orch, "fetch_horizons_reference", mock_horizons_solar), \
             patch.object(orch, "run_adapter", return_value=mock_adapter_result(10)), \
             patch.object(orch, "ensure_rust_adapters_built"):
            results = orch.run_experiment_planet_position(
                "mars_position", n=10, seed=42, run_perf=False
            )
            assert len(results) > 0
            for r in results:
                assert r["experiment"] == "mars_position"
                assert r["reference_library"] == "jpl_horizons"
