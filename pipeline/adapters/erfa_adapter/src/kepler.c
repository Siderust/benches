#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: kepler_solver                                           */
/* Kepler equation M→E→ν self-consistency                              */
/* Input per line: M_rad  e                                            */
/* ------------------------------------------------------------------ */

void run_kepler_solver(void) {
    /* Removed: ERFA exposes no public Kepler-equation solver.  Catalog
     * marks (erfa, kepler_solver) as support="unsupported" so this
     * experiment never reaches the public scoreboard.  We still drain
     * stdin so the orchestrator's stream protocol stays in sync. */
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    for (int i = 0; i < n; i++) {
        double M_rad, e;
        if (scanf("%lf %lf", &M_rad, &e) != 2) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }
    printf("{\"experiment\":\"kepler_solver\",\"library\":\"erfa\",");
    printf("\"model\":\"unsupported\",\"status\":\"unsupported\",");
    printf("\"reason\":\"ERFA does not expose a public Kepler-equation solver; row excluded by capability catalog.\",");
    printf("\"count\":0,\"cases\":[]}\n");
}
void run_kepler_solver_perf(void) {
    /* Removed: see run_kepler_solver above. */
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    for (int i = 0; i < n; i++) {
        double M_rad, e;
        if (scanf("%lf %lf", &M_rad, &e) != 2) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }
    printf("{\"experiment\":\"kepler_solver_perf\",\"library\":\"erfa\",");
    printf("\"status\":\"unsupported\",\"reason\":\"ERFA does not expose a public Kepler-equation solver.\",");
    printf("\"count\":0,\"total_ns\":0,\"per_op_ns\":0,\"throughput_ops_s\":0,\"_sink\":0.0}\n");
}
