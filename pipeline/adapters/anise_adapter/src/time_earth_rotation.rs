use crate::common::skip_experiment;

pub(crate) fn dispatch(experiment: &str, lines: &mut impl Iterator<Item = String>) -> bool {
    match experiment {
        "frame_rotation_bpn" => skip_experiment(
            lines,
            "frame_rotation_bpn",
            "ANISE adapter does not expose IAU2006/2000A BPN rotation in this lab integration",
        ),
        "frame_rotation_bpn_perf" => skip_experiment(
            lines,
            "frame_rotation_bpn_perf",
            "ANISE adapter does not expose IAU2006/2000A BPN rotation in this lab integration",
        ),
        "gmst_era" => skip_experiment(
            lines,
            "gmst_era",
            "ANISE adapter does not expose direct GMST/ERA benchmark API in this lab integration",
        ),
        "gmst_era_perf" => skip_experiment(
            lines,
            "gmst_era_perf",
            "ANISE adapter does not expose direct GMST/ERA benchmark API in this lab integration",
        ),
        _ => return false,
    }
    true
}
