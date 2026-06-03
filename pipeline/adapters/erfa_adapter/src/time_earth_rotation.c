#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: frame_rotation_bpn                                      */
/* Computes the Bias-Precession-Nutation matrix using IAU 2006/2000A   */
/* and applies it to input direction vectors.                          */
/* ------------------------------------------------------------------ */

void run_frame_rotation_bpn(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    /* Header */
    printf("{\"experiment\":\"frame_rotation_bpn\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_2000A\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }

        /* Split JD into two-part form for best precision */
        double date1 = 2451545.0;           /* J2000.0 */
        double date2 = jd_tt - 2451545.0;

        /* Compute BPN matrix (GCRS → CIRS), IAU 2006/2000A */
        double rnpb[3][3];
        eraPnm06a(date1, date2, rnpb);

        /* Apply BPN to input direction vector */
        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(rnpb, vin, vout);
        normalize3(vout);

        /* Also compute inverse (CIRS → GCRS) for closure test */
        double vinv[3];
        /* Transpose of rnpb */
        double rnpb_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                rnpb_t[r][c] = rnpb[c][r];
        mv3(rnpb_t, vout, vinv);
        normalize3(vinv);

        double closure_rad = ang_sep(vin, vinv);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e,", closure_rad);
        printf("\"matrix\":[[%.17e,%.17e,%.17e],[%.17e,%.17e,%.17e],[%.17e,%.17e,%.17e]]}",
            rnpb[0][0], rnpb[0][1], rnpb[0][2],
            rnpb[1][0], rnpb[1][1], rnpb[1][2],
            rnpb[2][0], rnpb[2][1], rnpb[2][2]);
    }

    printf("\n]}\n");
}

/* ------------------------------------------------------------------ */
/* Experiment: gmst_era                                                */
/* Computes GMST (IAU 2006) and ERA (IAU 2000) at given epochs.        */
/* ------------------------------------------------------------------ */

void run_gmst_era(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"gmst_era\",\"library\":\"erfa\",");
    printf("\"model\":\"GMST=IAU2006, ERA=IAU2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt;
        if (scanf("%lf %lf", &jd_ut1, &jd_tt) != 2) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }

        double ut1_hi = 2451545.0;
        double ut1_lo = jd_ut1 - 2451545.0;
        double tt_hi  = 2451545.0;
        double tt_lo  = jd_tt - 2451545.0;

        double gmst = eraGmst06(ut1_hi, ut1_lo, tt_hi, tt_lo);
        double era  = eraEra00(ut1_hi, ut1_lo);
        double gast = eraGst06a(ut1_hi, ut1_lo, tt_hi, tt_lo);

        if (i > 0) printf(",\n");
        printf("{\"jd_ut1\":%.15f,\"jd_tt\":%.15f,", jd_ut1, jd_tt);
        printf("\"gmst_rad\":%.17e,\"era_rad\":%.17e,\"gast_rad\":%.17e}", gmst, era, gast);
    }

    printf("\n]}\n");
}
/* ------------------------------------------------------------------ */
/* Performance timing helper                                           */
/* ------------------------------------------------------------------ */

void run_frame_rotation_bpn_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    /* Read all inputs */
    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
        jds[i] = jd_tt;
        vecs[3*i+0] = vx; vecs[3*i+1] = vy; vecs[3*i+2] = vz;
    }

    /* Warm-up: use GAST, matching functional equ_horizontal path. */
    for (int i = 0; i < n && i < 100; i++) {
        double rnpb[3][3];
        eraPnm06a(2451545.0, jds[i] - 2451545.0, rnpb);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double vout[3];
    for (int i = 0; i < n; i++) {
        double rnpb[3][3];
        eraPnm06a(2451545.0, jds[i] - 2451545.0, rnpb);
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(rnpb, vin, vout);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"frame_rotation_bpn_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,", (double)n / (elapsed_ns * 1e-9));
    /* Dummy use of vout to prevent optimization */
    printf("\"_sink\":%.17e}\n", vout[0]);

    free(jds);
    free(vecs);
}
void run_gmst_era_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jd_ut1_arr = malloc(n * sizeof(double));
    double *jd_tt_arr = malloc(n * sizeof(double));

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt;
        if (scanf("%lf %lf", &jd_ut1, &jd_tt) != 2) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
        jd_ut1_arr[i] = jd_ut1;
        jd_tt_arr[i] = jd_tt;
    }

    /* Warm-up */
    for (int i = 0; i < n && i < 100; i++) {
        double gmst = eraGmst06(2451545.0, jd_ut1_arr[i] - 2451545.0,
                                2451545.0, jd_tt_arr[i] - 2451545.0);
        (void)gmst;
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double gmst = eraGmst06(2451545.0, jd_ut1_arr[i] - 2451545.0,
                                2451545.0, jd_tt_arr[i] - 2451545.0);
        sink += gmst;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"gmst_era_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jd_ut1_arr);
    free(jd_tt_arr);
}
/* ================================================================== */
/* NEW COORDINATE-TRANSFORM EXPERIMENTS                                */
/* ================================================================== */

/* ------------------------------------------------------------------ */
/* Experiment: frame_bias                                              */
/* ICRS ↔ EquatorialMeanJ2000 via eraBp06 bias matrix (rb)            */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_frame_bias(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"frame_bias\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_bias\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        /* Frame bias matrix from eraBp06 */
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(2451545.0, 0.0, rb, rp, rbp);  /* bias is epoch-independent */

        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(rb, vin, vout);
        normalize3(vout);

        /* Closure via transpose */
        double rb_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                rb_t[r][c] = rb[c][r];
        double vback[3];
        mv3(rb_t, vout, vback);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_frame_bias_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf", &jds[i], &vecs[3*i], &vecs[3*i+1], &vecs[3*i+2]) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    for (int i = 0; i < n && i < 100; i++) {
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(2451545.0, 0.0, rb, rp, rbp);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double vout[3];
    for (int i = 0; i < n; i++) {
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(2451545.0, 0.0, rb, rp, rbp);
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(rb, vin, vout);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"frame_bias_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), vout[0]);
    free(jds); free(vecs);
}

/* ------------------------------------------------------------------ */
/* Experiment: precession                                              */
/* EquatorialMeanJ2000 → EquatorialMeanOfDate via eraBp06 pure rp      */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_precession(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"precession\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_precession\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(date1, date2, rb, rp, rbp);

        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(rp, vin, vout);
        normalize3(vout);

        /* Closure via transpose */
        double rp_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                rp_t[r][c] = rp[c][r];
        double vback[3];
        mv3(rp_t, vout, vback);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_precession_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf", &jds[i], &vecs[3*i], &vecs[3*i+1], &vecs[3*i+2]) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    for (int i = 0; i < n && i < 100; i++) {
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(2451545.0, jds[i] - 2451545.0, rb, rp, rbp);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double vout[3];
    for (int i = 0; i < n; i++) {
        double rb[3][3], rp[3][3], rbp[3][3];
        eraBp06(2451545.0, jds[i] - 2451545.0, rb, rp, rbp);
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(rp, vin, vout);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"precession_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), vout[0]);
    free(jds); free(vecs);
}

/* ------------------------------------------------------------------ */
/* Experiment: nutation                                                */
/* EquatorialMeanOfDate → EquatorialTrueOfDate via eraNum06a           */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_nutation(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"nutation\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_2000A_nutation\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;
        double rn[3][3];
        eraNum06a(date1, date2, rn);

        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(rn, vin, vout);
        normalize3(vout);

        double rn_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                rn_t[r][c] = rn[c][r];
        double vback[3];
        mv3(rn_t, vout, vback);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_nutation_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf", &jds[i], &vecs[3*i], &vecs[3*i+1], &vecs[3*i+2]) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    for (int i = 0; i < n && i < 100; i++) {
        double rn[3][3];
        eraNum06a(2451545.0, jds[i] - 2451545.0, rn);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double vout[3];
    for (int i = 0; i < n; i++) {
        double rn[3][3];
        eraNum06a(2451545.0, jds[i] - 2451545.0, rn);
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(rn, vin, vout);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"nutation_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), vout[0]);
    free(jds); free(vecs);
}
/* ================================================================== */
/* 13 NEW DIRECTION-VECTOR TRANSFORM EXPERIMENTS                       */
/* All share: input = jd_tt vx vy vz, output = rotated direction       */
/* ================================================================== */

/* Helper: generic direction-vector accuracy experiment.
 * fn_matrix(jd_tt, date1, date2, mat) fills mat with the 3x3 rotation.
 */
typedef void (*matrix_fn_t)(double jd_tt, double date1, double date2, double mat[3][3]);

static void _run_dir_accuracy(const char *exp_name, const char *model, matrix_fn_t fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"%s\",\"library\":\"erfa\",", exp_name);
    printf("\"model\":\"%s\",", model);
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;
        double mat[3][3];
        fn(jd_tt, date1, date2, mat);

        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(mat, vin, vout);
        normalize3(vout);

        /* Closure via transpose */
        double mat_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                mat_t[r][c] = mat[c][r];
        double vback[3];
        mv3(mat_t, vout, vback);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

static void _run_dir_perf(const char *exp_name, matrix_fn_t fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf", &jds[i], &vecs[3*i], &vecs[3*i+1], &vecs[3*i+2]) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    /* warmup */
    for (int i = 0; i < n && i < 100; i++) {
        double mat[3][3];
        fn(jds[i], 2451545.0, jds[i] - 2451545.0, mat);
    }

    struct timespec t0, t1;
    double vout[3];
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < n; i++) {
        double date1 = 2451545.0, date2 = jds[i] - 2451545.0;
        double mat[3][3];
        fn(jds[i], date1, date2, mat);
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(mat, vin, vout);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"%s_perf\",\"library\":\"erfa\",", exp_name);
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), vout[0]);
    free(jds); free(vecs);
}

/* --- Matrix factory functions --- */

static void mat_inv_frame_bias(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rb[3][3], rp[3][3], rbp[3][3];
    eraBp06(2451545.0, 0.0, rb, rp, rbp);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rb[c][r]; /* transpose */
}

static void mat_inv_precession(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rb[3][3], rp[3][3], rbp[3][3];
    eraBp06(d1, d2, rb, rp, rbp);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rp[c][r];
}

static void mat_inv_nutation(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rn[3][3];
    eraNum06a(d1, d2, rn);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rn[c][r];
}

static void mat_inv_bpn(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rnpb[3][3];
    eraPnm06a(d1, d2, rnpb);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rnpb[c][r];
}

static void mat_inv_icrs_ecl_j2000(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt; (void)d1; (void)d2;
    double rm[3][3];
    eraEcm06(2451545.0, 0.0, rm);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rm[c][r];
}

static void mat_obliquity(double jd_tt, double d1, double d2, double m[3][3]) {
    /* EclMeanJ2000 → EqMeanJ2000: Rx(+eps0) */
    (void)jd_tt; (void)d1; (void)d2;
    double eps = eraObl06(2451545.0, 0.0);
    double c = cos(eps), s = sin(eps);
    m[0][0]=1; m[0][1]=0;  m[0][2]=0;
    m[1][0]=0; m[1][1]=c;  m[1][2]=-s;
    m[2][0]=0; m[2][1]=s;  m[2][2]=c;
}

static void mat_inv_obliquity(double jd_tt, double d1, double d2, double m[3][3]) {
    /* EqMeanJ2000 → EclMeanJ2000: Rx(-eps0) */
    (void)jd_tt; (void)d1; (void)d2;
    double eps = eraObl06(2451545.0, 0.0);
    double c = cos(eps), s = sin(eps);
    m[0][0]=1; m[0][1]=0; m[0][2]=0;
    m[1][0]=0; m[1][1]=c; m[1][2]=s;
    m[2][0]=0; m[2][1]=-s; m[2][2]=c;
}

static void mat_bias_precession(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rb[3][3], rp[3][3], rbp[3][3];
    eraBp06(d1, d2, rb, rp, rbp);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rbp[r][c];
}

static void mat_inv_bias_precession(double jd_tt, double d1, double d2, double m[3][3]) {
    (void)jd_tt;
    double rb[3][3], rp[3][3], rbp[3][3];
    eraBp06(d1, d2, rb, rp, rbp);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rbp[c][r];
}

static void mat_precession_nutation(double jd_tt, double d1, double d2, double m[3][3]) {
    /* EqMeanJ2000 → EqTrueOfDate: P × N composed (= NxP product) */
    (void)jd_tt;
    double rb[3][3], rp[3][3], rbp[3][3], rn[3][3];
    eraBp06(d1, d2, rb, rp, rbp);
    eraNum06a(d1, d2, rn);
    /* m = rn × rp */
    for (int r = 0; r < 3; r++)
        for (int c = 0; c < 3; c++) {
            m[r][c] = 0;
            for (int k = 0; k < 3; k++)
                m[r][c] += rn[r][k] * rp[k][c];
        }
}

static void mat_inv_precession_nutation(double jd_tt, double d1, double d2, double m[3][3]) {
    double rpn[3][3];
    mat_precession_nutation(jd_tt, d1, d2, rpn);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rpn[c][r];
}

static void mat_inv_icrs_ecl_tod(double jd_tt, double d1, double d2, double m[3][3]) {
    /* EclTrueOfDate → ICRS: transpose(eraEcm06) */
    (void)jd_tt;
    double rm[3][3];
    eraEcm06(d1, d2, rm);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) m[r][c] = rm[c][r];
}

static void mat_inv_equ_ecl(double jd_tt, double d1, double d2, double m[3][3]) {
    /* EclTrueOfDate → EqMeanOfDate: RBP × ECM06^T
     * ECM06 = ICRS→Ecl.  RBP = ICRS→EqMeanOfDate.
     * Ecl→EqMeanOfDate = RBP × ECM06^T
     */
    (void)jd_tt;
    double rm[3][3], rm_t[3][3];
    double rb[3][3], rp[3][3], rbp[3][3];
    eraEcm06(d1, d2, rm);
    eraBp06(d1, d2, rb, rp, rbp);
    for (int r = 0; r < 3; r++) for (int c = 0; c < 3; c++) rm_t[r][c] = rm[c][r];
    /* m = rbp × rm_t */
    for (int r = 0; r < 3; r++)
        for (int c = 0; c < 3; c++) {
            m[r][c] = 0;
            for (int k = 0; k < 3; k++)
                m[r][c] += rbp[r][k] * rm_t[k][c];
        }
}

/* --- Experiment entry points (dispatched from main) --- */
void run_inv_frame_bias(void)        { _run_dir_accuracy("inv_frame_bias",        "IAU_2006_inv_bias",       mat_inv_frame_bias); }
void run_inv_frame_bias_perf(void)   { _run_dir_perf("inv_frame_bias",        mat_inv_frame_bias); }
void run_inv_precession(void)        { _run_dir_accuracy("inv_precession",        "IAU_2006_inv_prec",       mat_inv_precession); }
void run_inv_precession_perf(void)   { _run_dir_perf("inv_precession",        mat_inv_precession); }
void run_inv_nutation(void)          { _run_dir_accuracy("inv_nutation",          "IAU_2000A_inv_nut",       mat_inv_nutation); }
void run_inv_nutation_perf(void)     { _run_dir_perf("inv_nutation",          mat_inv_nutation); }
void run_inv_bpn(void)               { _run_dir_accuracy("inv_bpn",               "IAU_2006_inv_bpn",        mat_inv_bpn); }
void run_inv_bpn_perf(void)          { _run_dir_perf("inv_bpn",               mat_inv_bpn); }
void run_inv_icrs_ecl_j2000(void)    { _run_dir_accuracy("inv_icrs_ecl_j2000",    "IAU_2006_inv_ecl_j2000",  mat_inv_icrs_ecl_j2000); }
void run_inv_icrs_ecl_j2000_perf(void){ _run_dir_perf("inv_icrs_ecl_j2000",    mat_inv_icrs_ecl_j2000); }
void run_obliquity(void)             { _run_dir_accuracy("obliquity",             "IAU_2006_obliquity",      mat_obliquity); }
void run_obliquity_perf(void)        { _run_dir_perf("obliquity",             mat_obliquity); }
void run_inv_obliquity(void)         { _run_dir_accuracy("inv_obliquity",         "IAU_2006_inv_obliq",      mat_inv_obliquity); }
void run_inv_obliquity_perf(void)    { _run_dir_perf("inv_obliquity",         mat_inv_obliquity); }
void run_bias_precession(void)       { _run_dir_accuracy("bias_precession",       "IAU_2006_bias_prec",      mat_bias_precession); }
void run_bias_precession_perf(void)  { _run_dir_perf("bias_precession",       mat_bias_precession); }
void run_inv_bias_precession(void)   { _run_dir_accuracy("inv_bias_precession",   "IAU_2006_inv_bias_prec",  mat_inv_bias_precession); }
void run_inv_bias_precession_perf(void){ _run_dir_perf("inv_bias_precession",   mat_inv_bias_precession); }
void run_precession_nutation(void)   { _run_dir_accuracy("precession_nutation",   "IAU_2006_prec_nut",       mat_precession_nutation); }
void run_precession_nutation_perf(void){ _run_dir_perf("precession_nutation",   mat_precession_nutation); }
void run_inv_precession_nutation(void){ _run_dir_accuracy("inv_precession_nutation","IAU_2006_inv_prec_nut", mat_inv_precession_nutation); }
void run_inv_precession_nutation_perf(void){ _run_dir_perf("inv_precession_nutation",mat_inv_precession_nutation); }
void run_inv_icrs_ecl_tod(void)      { _run_dir_accuracy("inv_icrs_ecl_tod",      "IAU_2006_inv_ecl_tod",    mat_inv_icrs_ecl_tod); }
void run_inv_icrs_ecl_tod_perf(void) { _run_dir_perf("inv_icrs_ecl_tod",      mat_inv_icrs_ecl_tod); }
void run_inv_equ_ecl(void)           { _run_dir_accuracy("inv_equ_ecl",           "IAU_2006_inv_equ_ecl",    mat_inv_equ_ecl); }
void run_inv_equ_ecl_perf(void)      { _run_dir_perf("inv_equ_ecl",           mat_inv_equ_ecl); }

