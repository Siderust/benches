#include "common.h"

static int planet_geocentric_ra_dec_dist(double jd_tt, int np,
                                         double *ra, double *dec, double *dist_au) {
    double date1 = 2451545.0, date2 = jd_tt - 2451545.0;
    double earth_pvh[2][3], earth_pvb[2][3], planet_pv[2][3];
    eraEpv00(date1, date2, earth_pvh, earth_pvb);
    int status = eraPlan94(date1, date2, np, planet_pv);

    double gx = planet_pv[0][0] - earth_pvh[0][0];
    double gy = planet_pv[0][1] - earth_pvh[0][1];
    double gz = planet_pv[0][2] - earth_pvh[0][2];
    *dist_au = sqrt(gx*gx + gy*gy + gz*gz);
    *ra = normalize_angle(atan2(gy, gx));
    *dec = asin(gz / *dist_au);
    return status;
}
/* ------------------------------------------------------------------ */
/* Experiment: solar_position                                          */
/* Apparent geocentric Sun RA/Dec using ERFA epv00                     */
/* (epv00 returns BCRS-aligned equatorial vectors, not ecliptic)       */
/* Input per line: jd_tt                                               */
/* ------------------------------------------------------------------ */

void run_solar_position(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"solar_position\",\"library\":\"erfa\",");
    printf("\"model\":\"ERFA_epv00_analytic\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;

        double pvh[2][3], pvb[2][3];
        eraEpv00(date1, date2, pvh, pvb);

        /* Sun geocentric ≈ –Earth heliocentric (BCRS equatorial) */
        double sx = -pvh[0][0], sy = -pvh[0][1], sz = -pvh[0][2];
        double dist_au = sqrt(sx*sx + sy*sy + sz*sz);
        double ra  = normalize_angle(atan2(sy, sx));
        double dec = asin(sz / dist_au);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra, dec, dist_au);
    }
    printf("\n]}\n");
}

/* ------------------------------------------------------------------ */
/* Experiment: lunar_position                                          */
/* Geocentric Moon RA/Dec using ERFA eraMoon98 (Meeus-based IAU impl). */
/* Input per line: jd_tt                                               */
/* ------------------------------------------------------------------ */

void run_lunar_position(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"lunar_position\",\"library\":\"erfa\",");
    printf("\"model\":\"ERFA_moon98\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double date1 = 2451545.0, date2 = jd_tt - 2451545.0;

        /* eraMoon98: geocentric Moon in GCRS (same as J2000 mean equator /
           equinox to within 23 mas).  pv[0] = position (AU), pv[1] = velocity. */
        double pv[2][3];
        eraMoon98(date1, date2, pv);

        double x = pv[0][0], y = pv[0][1], z = pv[0][2];
        double dist_au = sqrt(x*x + y*y + z*z);
        double dist_km = dist_au * 149597870.700;
        double ra  = normalize_angle(atan2(y, x));
        double dec = asin(z / dist_au);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_km\":%.17e}", ra, dec, dist_km);
    }
    printf("\n]}\n");
}

void run_planet_position(const char *experiment, const char *planet_name, int np) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"%s\",\"library\":\"erfa\",", experiment);
    printf("\"model\":\"ERFA_plan94_%s_analytic\",", planet_name);
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, ra, dec, dist_au;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        planet_geocentric_ra_dec_dist(jd_tt, np, &ra, &dec, &dist_au);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra, dec, dist_au);
    }
    printf("\n]}\n");
}
void run_solar_position_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Warm-up: include full RA/Dec/dist extraction (same scope as functional). */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double pvh[2][3], pvb[2][3];
        eraEpv00(2451545.0, jds[i] - 2451545.0, pvh, pvb);
        double sx = -pvh[0][0], sy = -pvh[0][1], sz = -pvh[0][2];
        double dist_au = sqrt(sx*sx + sy*sy + sz*sz);
        double ra = normalize_angle(atan2(sy, sx));
        double dec = asin(sz / dist_au);
        (void)ra;
        (void)dec;
    }

    /* Timed run — perf contract: compute RA + Dec + distance */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double pvh[2][3], pvb[2][3];
        eraEpv00(2451545.0, jds[i] - 2451545.0, pvh, pvb);
        double sx = -pvh[0][0], sy = -pvh[0][1], sz = -pvh[0][2];
        double dist_au = sqrt(sx*sx + sy*sy + sz*sz);
        double ra = normalize_angle(atan2(sy, sx));
        double dec = asin(sz / dist_au);
        sink += ra + dec + dist_au;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"solar_position_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
}

void run_lunar_position_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Warm-up: use eraMoon98, same as the accuracy benchmark. */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double date1 = 2451545.0, date2 = jds[i] - 2451545.0;
        double pv[2][3];
        eraMoon98(date1, date2, pv);
        double x = pv[0][0], y = pv[0][1], z = pv[0][2];
        double dist_au = sqrt(x*x + y*y + z*z);
        double ra  = normalize_angle(atan2(y, x));
        double dec = asin(z / dist_au);
        (void)ra;
        (void)dec;
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double date1 = 2451545.0, date2 = jds[i] - 2451545.0;
        double pv[2][3];
        eraMoon98(date1, date2, pv);
        double x = pv[0][0], y = pv[0][1], z = pv[0][2];
        double dist_au = sqrt(x*x + y*y + z*z);
        double ra  = normalize_angle(atan2(y, x));
        double dec = asin(z / dist_au);
        sink += ra + dec;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"lunar_position_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
}

void run_planet_position_perf(const char *experiment, int np) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double ra, dec, dist_au;
        planet_geocentric_ra_dec_dist(jds[i], np, &ra, &dec, &dist_au);
        (void)ra;
        (void)dec;
        (void)dist_au;
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double ra, dec, dist_au;
        planet_geocentric_ra_dec_dist(jds[i], np, &ra, &dec, &dist_au);
        sink += ra + dec + dist_au;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"%s_perf\",\"library\":\"erfa\",", experiment);
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
}
