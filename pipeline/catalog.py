"""Capability catalog loader.

The catalog at ``pipeline/catalog.toml`` is the single source of truth for
what the lab publishes.  This module exposes a typed view of that file plus
the ``CandidateRegistry`` used by the orchestrator and the tests.

The catalog is *additive* to the existing pipeline: the orchestrator still
drives candidate selection through ``candidate_adapters()``, but it queries
the registry for ``support_status``, ``parity``, ``api_surface`` and the
canonical ``candidate_id`` so that:

  - candidates with ``support = unsupported`` are dropped before the row is
    even built (no fabricated data leaves the adapter),
  - candidates with ``support = runtime-blocked`` are excluded from adapter
    runs and listed in the manifest ``excluded_candidates`` (not ranked),
  - reference-only adapters (``api_surface = reference``) never appear as
    a candidate row in the public scoreboard,
  - downstream consumers (scorecard, frontend) read ``candidate_id`` and
    ``api_surface`` from the catalog instead of parsing label strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]


CATALOG_PATH = Path(__file__).resolve().parent / "catalog.toml"


VALID_API_SURFACES = {"public", "reference", "diagnostic"}
VALID_LANES = {"geometric_vector", "apparent_observer"}
# Parity taxonomy (audit issue #4).  The reference for ephemeris lanes is JPL
# Horizons DE441.  A candidate is only ``exact-same-kernel`` when its resolved
# source kernel/model is *identical* to the reference; a JPL DE kernel of a
# different version (e.g. DE440 vs the DE441 reference) is ``same-family-jpl``
# — comparable, ranked in the broad view, but NEVER crowned in the strict
# exact-model view.  ``best-available`` is a different model with the same
# observable; ``model-mismatch`` is not comparable; ``reference`` is the
# reference row itself.
VALID_PARITIES = {
    "exact-same-kernel", "same-family-jpl", "best-available",
    "model-mismatch", "diagnostic-only", "reference",
}
# Parities eligible for accuracy ranking (broad view).
RANKABLE_PARITIES = {"exact-same-kernel", "same-family-jpl", "best-available"}
VALID_SUPPORT = {"supported", "runtime-blocked", "unsupported"}


@dataclass(frozen=True)
class CandidateEntry:
    """One catalog row: a single (candidate_id, experiment) decision."""
    id: str                       # e.g. "siderust:de440"
    library: str                  # e.g. "siderust"
    experiment: str               # e.g. "lunar_position"
    api_surface: str              # public | reference | diagnostic
    api_method: str               # exact upstream symbol
    model: str
    source: str
    lane: str
    parity: str
    support: str                  # supported | runtime-blocked | unsupported
    exclusion_reason: str = ""
    display: str = ""
    description: str = ""

    @property
    def is_published(self) -> bool:
        """True iff this entry should produce a row in the public scoreboard."""
        return (
            self.support == "supported"
            and self.api_surface in {"public", "diagnostic"}
        )

    @property
    def is_rankable(self) -> bool:
        """True iff this entry is eligible to be ranked against the reference."""
        return (
            self.support == "supported"
            and self.api_surface == "public"
            and self.parity in RANKABLE_PARITIES
        )


def _coerce_methods(raw: dict[str, Any], default_method: str) -> dict[str, str]:
    """Return per-experiment method overrides, falling back to default_method."""
    out: dict[str, str] = {}
    methods = raw.get("api_methods")
    if isinstance(methods, dict):
        for k, v in methods.items():
            if isinstance(v, str):
                out[k] = v
    return out


def _expand_entry(raw: dict[str, Any]) -> list[CandidateEntry]:
    """Expand one [[candidate]] block into one entry per experiment."""
    cid = str(raw["id"])
    library = str(raw["library"])
    experiments = list(raw.get("experiments", []))
    if not experiments:
        return []

    api_surface = str(raw.get("api_surface", ""))
    if api_surface not in VALID_API_SURFACES:
        raise ValueError(
            f"catalog: candidate {cid!r}: unknown api_surface {api_surface!r}; "
            f"allowed: {sorted(VALID_API_SURFACES)}"
        )

    lane = str(raw.get("lane", ""))
    if lane not in VALID_LANES:
        raise ValueError(
            f"catalog: candidate {cid!r}: unknown lane {lane!r}; "
            f"allowed: {sorted(VALID_LANES)}"
        )

    parity = str(raw.get("parity", ""))
    if parity not in VALID_PARITIES:
        raise ValueError(
            f"catalog: candidate {cid!r}: unknown parity {parity!r}; "
            f"allowed: {sorted(VALID_PARITIES)}"
        )

    support = str(raw.get("support", ""))
    if support not in VALID_SUPPORT:
        raise ValueError(
            f"catalog: candidate {cid!r}: unknown support {support!r}; "
            f"allowed: {sorted(VALID_SUPPORT)}"
        )

    if support != "supported" and not raw.get("exclusion_reason"):
        raise ValueError(
            f"catalog: candidate {cid!r} has support={support!r} but no "
            f"exclusion_reason — every non-supported entry MUST document why."
        )

    default_method = str(raw.get("api_method", ""))
    method_overrides = _coerce_methods(raw, default_method)
    model = str(raw.get("model", ""))
    source = str(raw.get("source", ""))
    display = str(raw.get("display", ""))
    description = str(raw.get("description", ""))
    exclusion = str(raw.get("exclusion_reason", ""))

    entries: list[CandidateEntry] = []
    for exp in experiments:
        method = method_overrides.get(exp, default_method) or "(unspecified)"
        entries.append(CandidateEntry(
            id=cid,
            library=library,
            experiment=str(exp),
            api_surface=api_surface,
            api_method=method,
            model=model,
            source=source,
            lane=lane,
            parity=parity,
            support=support,
            exclusion_reason=exclusion,
            display=display,
            description=description,
        ))
    return entries


@dataclass
class CandidateRegistry:
    """Indexed, queryable view of catalog.toml."""

    entries: list[CandidateEntry] = field(default_factory=list)
    _by_id_exp: dict[tuple[str, str], CandidateEntry] = field(default_factory=dict)
    _by_experiment: dict[str, list[CandidateEntry]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str = CATALOG_PATH) -> "CandidateRegistry":
        path = Path(path)
        with path.open("rb") as f:
            raw = tomllib.load(f)
        candidates = raw.get("candidate", [])
        entries: list[CandidateEntry] = []
        for block in candidates:
            entries.extend(_expand_entry(block))
        return cls.from_entries(entries)

    @classmethod
    def from_entries(cls, entries: Iterable[CandidateEntry]) -> "CandidateRegistry":
        reg = cls()
        for e in entries:
            key = (e.id, e.experiment)
            if key in reg._by_id_exp:
                raise ValueError(
                    f"catalog: duplicate (candidate_id={e.id!r}, "
                    f"experiment={e.experiment!r}). Each tuple must be unique."
                )
            reg._by_id_exp[key] = e
            reg._by_experiment.setdefault(e.experiment, []).append(e)
            reg.entries.append(e)
        return reg

    # -- query API ---------------------------------------------------------
    def candidates_for(self, experiment: str) -> list[CandidateEntry]:
        return list(self._by_experiment.get(experiment, []))

    def published_candidates_for(self, experiment: str) -> list[CandidateEntry]:
        """Entries that should appear as a row (supported public/diagnostic)."""
        return [e for e in self.candidates_for(experiment) if e.is_published]

    def get(self, candidate_id: str, experiment: str) -> CandidateEntry | None:
        return self._by_id_exp.get((candidate_id, experiment))

    def support_status(self, candidate_id: str, experiment: str) -> str:
        e = self.get(candidate_id, experiment)
        if e is None:
            return "unknown"
        return e.support

    def parity_for(self, candidate_id: str, experiment: str) -> str:
        e = self.get(candidate_id, experiment)
        return e.parity if e else "unknown"

    def lane_for(self, candidate_id: str, experiment: str) -> str | None:
        e = self.get(candidate_id, experiment)
        return e.lane if e else None

    def api_surface_for(self, candidate_id: str, experiment: str) -> str:
        e = self.get(candidate_id, experiment)
        return e.api_surface if e else "unknown"

    def all_candidate_ids(self) -> set[str]:
        return {e.id for e in self.entries}

    def all_experiments(self) -> set[str]:
        return set(self._by_experiment.keys())


_DEFAULT: CandidateRegistry | None = None


def default_registry() -> CandidateRegistry:
    """Lazily-loaded process-wide registry."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CandidateRegistry.load()
    return _DEFAULT


def reload_default() -> CandidateRegistry:
    """Force-reload the default registry (used by tests)."""
    global _DEFAULT
    _DEFAULT = CandidateRegistry.load()
    return _DEFAULT
