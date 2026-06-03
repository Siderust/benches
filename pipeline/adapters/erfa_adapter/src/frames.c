#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: equ_ecl                                                 */
/* Equatorial (ICRS RA/Dec) ↔ Ecliptic (lon/lat), IAU 2006             */
/* Input per line: jd_tt  ra_rad  dec_rad                              */
/* ------------------------------------------------------------------ */

void run_equ_ecl(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"equ_ecl\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_ecliptic\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, ra_rad, dec_rad;
        if (scanf("%lf %lf %lf", &jd_tt, &ra_rad, &dec_rad) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;

        /* Forward: Equatorial → Ecliptic */
        double ecl_lon, ecl_lat;
        eraEqec06(date1, date2, ra_rad, dec_rad, &ecl_lon, &ecl_lat);

        /* Closure: Ecliptic → Equatorial */
        double ra_back, dec_back;
        eraEceq06(date1, date2, ecl_lon, ecl_lat, &ra_back, &dec_back);

        double v_in[3]   = { cos(dec_rad)*cos(ra_rad), cos(dec_rad)*sin(ra_rad), sin(dec_rad) };
        double v_back[3]  = { cos(dec_back)*cos(ra_back), cos(dec_back)*sin(ra_back), sin(dec_back) };
        double closure_rad = ang_sep(v_in, v_back);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"ra_rad\":%.17e,\"dec_rad\":%.17e,", jd_tt, ra_rad, dec_rad);
        printf("\"ecl_lon_rad\":%.17e,\"ecl_lat_rad\":%.17e,", ecl_lon, ecl_lat);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}
void run_equ_ecl_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *ras = malloc(n * sizeof(double));
    double *decs = malloc(n * sizeof(double));

    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf", &jds[i], &ras[i], &decs[i]) != 3) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Warm-up: match measured operation to functional path (Eqec06). */
    for (int i = 0; i < n && i < 100; i++) {
        double ecl_lon, ecl_lat;
        eraEqec06(2451545.0, jds[i] - 2451545.0, ras[i], decs[i], &ecl_lon, &ecl_lat);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double ecl_lon, ecl_lat;
        eraEqec06(2451545.0, jds[i] - 2451545.0, ras[i], decs[i], &ecl_lon, &ecl_lat);
        sink += ecl_lon;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"equ_ecl_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
    free(ras);
    free(decs);
}
/* ------------------------------------------------------------------ */
/* Experiment: icrs_ecl_j2000                                          */
/* ICRS → EclipticMeanJ2000 via eraEcm06 at J2000 (bias+obliquity)    */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_icrs_ecl_j2000(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"icrs_ecl_j2000\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_ecliptic_J2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    /* Ecliptic rotation at J2000 (time-independent for this experiment) */
    double rm[3][3];
    eraEcm06(2451545.0, 0.0, rm);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        double vout[3];
        mv3(rm, vin, vout);
        normalize3(vout);

        /* Convert output to ecliptic lon/lat */
        double ecl_lon = normalize_angle(atan2(vout[1], vout[0]));
        double ecl_lat = asin(vout[2]);

        /* Closure via transpose */
        double rm_t[3][3];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                rm_t[r][c] = rm[c][r];
        double vback[3];
        mv3(rm_t, vout, vback);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"ecl_lon_rad\":%.17e,\"ecl_lat_rad\":%.17e,", ecl_lon, ecl_lat);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_icrs_ecl_j2000_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *vecs = malloc(n * 3 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf", &jds[i], &vecs[3*i], &vecs[3*i+1], &vecs[3*i+2]) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    double rm[3][3];
    eraEcm06(2451545.0, 0.0, rm);

    for (int i = 0; i < n && i < 100; i++) {
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        double vout[3];
        mv3(rm, vin, vout);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double vout[3];
    for (int i = 0; i < n; i++) {
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        mv3(rm, vin, vout);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"icrs_ecl_j2000_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), vout[0]);
    free(jds); free(vecs);
}

/* ------------------------------------------------------------------ */
/* Experiment: icrs_ecl_tod                                            */
/* ICRS → EclipticTrueOfDate via eraEqec06 (full chain)                */
/* Input per line: jd_tt ra_rad dec_rad                                */
/* ------------------------------------------------------------------ */

void run_icrs_ecl_tod(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"icrs_ecl_tod\",\"library\":\"erfa\",");
    printf("\"model\":\"IAU_2006_ecliptic_of_date\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, ra_rad, dec_rad;
        if (scanf("%lf %lf %lf", &jd_tt, &ra_rad, &dec_rad) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;

        double ecl_lon, ecl_lat;
        eraEqec06(date1, date2, ra_rad, dec_rad, &ecl_lon, &ecl_lat);

        /* Closure */
        double ra_back, dec_back;
        eraEceq06(date1, date2, ecl_lon, ecl_lat, &ra_back, &dec_back);
        double v_in[3]  = { cos(dec_rad)*cos(ra_rad), cos(dec_rad)*sin(ra_rad), sin(dec_rad) };
        double v_bk[3]  = { cos(dec_back)*cos(ra_back), cos(dec_back)*sin(ra_back), sin(dec_back) };
        double closure_rad = ang_sep(v_in, v_bk);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"ra_rad\":%.17e,\"dec_rad\":%.17e,", jd_tt, ra_rad, dec_rad);
        printf("\"ecl_lon_rad\":%.17e,\"ecl_lat_rad\":%.17e,", ecl_lon, ecl_lat);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_icrs_ecl_tod_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    double *ras = malloc(n * sizeof(double));
    double *decs = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf", &jds[i], &ras[i], &decs[i]) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    for (int i = 0; i < n && i < 100; i++) {
        double ecl_lon, ecl_lat;
        eraEqec06(2451545.0, jds[i] - 2451545.0, ras[i], decs[i], &ecl_lon, &ecl_lat);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double ecl_lon, ecl_lat;
        eraEqec06(2451545.0, jds[i] - 2451545.0, ras[i], decs[i], &ecl_lon, &ecl_lat);
        sink += ecl_lon + ecl_lat;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"icrs_ecl_tod_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(jds); free(ras); free(decs);
}
