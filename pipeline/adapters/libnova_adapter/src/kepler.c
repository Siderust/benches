#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: kepler_solver                                           */
/* Kepler equation via libnova's Sinnott bisection method              */
/* Input per line: M_rad  e                                            */
/* ------------------------------------------------------------------ */

void run_kepler_solver(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"kepler_solver\",\"library\":\"libnova\",");
    printf("\"model\":\"Sinnott_bisection\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double M_rad, e;
        if (scanf("%lf %lf", &M_rad, &e) != 2) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        /* libnova uses degrees */
        double M_deg = M_rad * (180.0 / M_PI);
        double E_deg = ln_solve_kepler(e, M_deg);
        double nu_deg = ln_get_ell_true_anomaly(e, E_deg);

        double E_rad  = E_deg  * (M_PI / 180.0);
        double nu_rad = nu_deg * (M_PI / 180.0);

        /* Self-consistency: recompute M from E */
        double residual = fabs(E_rad - e * sin(E_rad) - M_rad);

        if (i > 0) printf(",\n");
        printf("{\"M_rad\":%.17e,\"e\":%.17e,", M_rad, e);
        printf("\"E_rad\":%.17e,\"nu_rad\":%.17e,", E_rad, nu_rad);
        printf("\"residual_rad\":%.17e,\"iters\":-1,\"converged\":%s}",
               residual, residual < 1e-6 ? "true" : "false");
    }
    printf("\n]}\n");
}

void run_kepler_solver_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *m_arr = malloc(n * sizeof(double));
    double *e_arr = malloc(n * sizeof(double));

    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf", &m_arr[i], &e_arr[i]) != 2) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Pre-convert M radians -> degrees for ln_solve_kepler API parity. */
    double *m_deg_arr = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        m_deg_arr[i] = m_arr[i] * (180.0 / M_PI);
    }

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double E = ln_solve_kepler(e_arr[i], m_deg_arr[i]);
        (void)E;
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double E = ln_solve_kepler(e_arr[i], m_deg_arr[i]);
        sink += E;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"kepler_solver_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(m_arr);
    free(e_arr);
    free(m_deg_arr);
}
