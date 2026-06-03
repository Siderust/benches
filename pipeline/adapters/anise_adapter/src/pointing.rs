use crate::common::skip_experiment;

pub(crate) fn dispatch(experiment: &str, lines: &mut impl Iterator<Item = String>) -> bool {
    match experiment {
        "equ_horizontal" => skip_experiment(
            lines,
            "equ_horizontal",
            "ANISE adapter does not include equatorial-horizontal benchmark path in this lab integration",
        ),
        "equ_horizontal_perf" => skip_experiment(
            lines,
            "equ_horizontal_perf",
            "ANISE adapter does not include equatorial-horizontal benchmark path in this lab integration",
        ),
        "horiz_to_equ" => skip_experiment(
            lines,
            "horiz_to_equ",
            "ANISE adapter does not include horizontal-equatorial benchmark path in this lab integration",
        ),
        "horiz_to_equ_perf" => skip_experiment(
            lines,
            "horiz_to_equ_perf",
            "ANISE adapter does not include horizontal-equatorial benchmark path in this lab integration",
        ),
        _ => return false,
    }
    true
}
