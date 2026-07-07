#!/usr/bin/env bash
# =================================================================
# Siderust Benchmark Laboratory - Build & Run Script
#
# Usage:
#   ./run.sh              # Build all + run core config
#   ./run.sh build        # Build only
#   ./run.sh run          # Run core config only (assumes built)
#   ./run.sh ci           # Build available adapters + run ci config
#   ./run.sh full         # Build available adapters + run full config
#   ./run.sh phase-b ci   # Build available adapters + run a Phase B matrix leg
#   ./run.sh pipeline/configs/ci.toml
#   ./run.sh run pipeline/configs/full_fast.toml --allow-dirty-publish
#   ./run.sh dev-delta
#   ./run.sh publication-delta --allow-partial-publish
# =================================================================

set -euo pipefail
cd "$(dirname "$0")"

LAB_ROOT="$(pwd)"
SIDERUST_BENCHES_CACHE="${SIDERUST_BENCHES_CACHE:-$LAB_ROOT/.benches_cache}"

# ---- Colours (safe for non-TTY) ----
if [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    RESET="\033[0m"
else
    BOLD="" GREEN="" YELLOW="" RESET=""
fi

log()  { echo -e "${GREEN}>${RESET} $*"; }
warn() { echo -e "${YELLOW}!${RESET} $*"; }

# ---- Benchmark cache (DE440 + Siderust datasets) ----
setup_benchmark_cache() {
    export SIDERUST_BENCHES_CACHE
    export ASTROPY_JPL_BSP_PATH="$SIDERUST_BENCHES_CACHE/kernels/de440.bsp"
    export ANISE_BSP_PATH="${ANISE_BSP_PATH:-$ASTROPY_JPL_BSP_PATH}"
    export SIDERUST_DATASETS_DIR="$SIDERUST_BENCHES_CACHE/siderust_datasets"

    mkdir -p "$SIDERUST_BENCHES_CACHE/kernels"
    mkdir -p "$SIDERUST_DATASETS_DIR/de440_dataset"
    if [ ! -e "$SIDERUST_DATASETS_DIR/de440_dataset/de440.bsp" ]; then
        ln -sf "$ASTROPY_JPL_BSP_PATH" "$SIDERUST_DATASETS_DIR/de440_dataset/de440.bsp"
    fi
}

# ---- Submodules ----
init_submodules_if_needed() {
    if [ "${FORCE_SUBMODULE_SYNC:-0}" = "1" ]; then
        warn "FORCE_SUBMODULE_SYNC=1 set: syncing submodules to pinned commits."
        git submodule update --init --recursive
        return
    fi

    if git submodule status --recursive | grep -q '^-'; then
        log "Initializing missing git submodules..."
        git submodule update --init --recursive
    else
        warn "Submodules already initialized; skipping sync to preserve local checkouts."
        warn "Set FORCE_SUBMODULE_SYNC=1 to reset submodules to pinned commits."
    fi
}

# ---- Build ----
build_all() {
    init_submodules_if_needed
    setup_benchmark_cache

    log "Building ERFA adapter (C)..."
    if ! make -C pipeline/adapters/erfa_adapter -j"$(nproc)" 2>&1 | tail -3; then
        warn "ERFA adapter build failed; experiments requiring it may be skipped."
    fi

    log "Building libnova adapter (C)..."
    if ! make -C pipeline/adapters/libnova_adapter -j"$(nproc)" 2>&1 | tail -3; then
        warn "libnova adapter build failed; libnova results may be skipped."
    fi

    log "Building Siderust adapter (Rust, release)..."
    if ! (cd pipeline/adapters/siderust_adapter && cargo build --release 2>&1 | tail -3); then
        warn "Siderust adapter build failed; Siderust results may be skipped."
    fi

    log "Building ANISE adapter (Rust, release)..."
    if ! (cd pipeline/adapters/anise_adapter && cargo build --release 2>&1 | tail -3); then
        warn "ANISE adapter build failed; ANISE results may be skipped."
    fi

    log "Setting up Python virtual environment..."
    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -q -r pipeline/requirements.txt

    log "Build step finished"
}

# ---- Run ----
resolve_config() {
    case "${1:-core}" in
        core|ci|diagnostic|full|dev-delta|publication-delta)
            case "$1" in
                dev-delta) echo "pipeline/configs/dev_delta.toml" ;;
                publication-delta) echo "pipeline/configs/publication_delta.toml" ;;
                *) echo "pipeline/configs/${1}.toml" ;;
            esac
            ;;
        *)
            echo "$1"
            ;;
    esac
}

run_all() {
    local CONFIG
    CONFIG="$(resolve_config "${1:-core}")"
    shift || true
    source .venv/bin/activate
    setup_benchmark_cache

    log "Running pipeline config: $CONFIG"
    python3 pipeline/run_pipeline.py --config "$CONFIG" "$@"

    log "Done. Results in results/"
}

# ---- Static export ----
export_static() {
    source .venv/bin/activate 2>/dev/null || true
    local OUT="${1:-static_export}"
    log "Exporting static lab data to $OUT"
    python3 -m pipeline.export_static --lab-root "$LAB_ROOT" --output "$OUT"
}

refresh_latest_results() {
    local SRC="${1:-static_export/latest}"
    local DST="$LAB_ROOT/latest_results"

    if [ ! -d "$SRC" ]; then
        warn "Skipping latest_results refresh: missing $SRC"
        return 0
    fi

    log "Refreshing latest_results from $SRC"
    rm -rf "$DST"
    cp -R "$SRC" "$DST"
}

# ---- Main ----
case "${1:-all}" in
    build)
        build_all
        ;;
    run)
        if [ "${2:-}" ] && [ "${2:0:1}" != "-" ]; then
            run_all "$2" "${@:3}"
        else
            run_all "pipeline/configs/core.toml" "${@:2}"
        fi
        ;;
    export)
        export_static "${2:-static_export}"
        refresh_latest_results "${2:-static_export}/latest"
        ;;
    phase-b|phase_b)
        build_all
        source .venv/bin/activate
        python3 pipeline/run_phase_b.py --matrix "${2:-ci}"
        ;;
    all|"")
        build_all
        run_all "${2:-pipeline/configs/core.toml}"
        export_static "static_export"
        refresh_latest_results "static_export/latest"
        ;;
    *)
        CONFIG="$(resolve_config "${1:-core}")"
        if [ -f "$CONFIG" ]; then
            build_all
            run_all "$CONFIG" "${@:2}"
            export_static "static_export"
            refresh_latest_results "static_export/latest"
        else
            echo "Usage: $0 [build|run|export|all|core|ci|diagnostic|full] [config.toml]"
            exit 1
        fi
        ;;
esac
