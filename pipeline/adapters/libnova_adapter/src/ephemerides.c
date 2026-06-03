#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: solar_position                                          */
/* Sun geocentric RA/Dec via libnova VSOP87                            */
/* Input per line: jd_tt                                               */
/* ------------------------------------------------------------------ */

void run_solar_position(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"solar_position\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_VSOP87\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        struct ln_equ_posn posn;
        ln_get_solar_equ_coords(jd_tt, &posn);

        /* libnova: ra in degrees (0..360), dec in degrees */
        double ra_rad  = posn.ra  * (M_PI / 180.0);
        double dec_rad = posn.dec * (M_PI / 180.0);

        /* Get distance */
        double dist_au = ln_get_earth_solar_dist(jd_tt);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra_rad, dec_rad, dist_au);
    }
    printf("\n]}\n");
}

/* ------------------------------------------------------------------ */
/* Experiment: lunar_position                                          */
/* Moon geocentric RA/Dec via libnova ELP 2000-82B                     */
/* Input per line: jd_tt                                               */
/* ------------------------------------------------------------------ */

void run_lunar_position(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"lunar_position\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_ELP2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        struct ln_equ_posn posn;
        ln_get_lunar_equ_coords(jd_tt, &posn);

        double ra_rad  = posn.ra  * (M_PI / 180.0);
        double dec_rad = posn.dec * (M_PI / 180.0);

        double dist_km = ln_get_lunar_earth_dist(jd_tt);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_km\":%.17e}", ra_rad, dec_rad, dist_km);
    }
    printf("\n]}\n");
}

void run_planet_position(const char *experiment,
                                const char *model,
                                planet_equ_fn_t equ_fn,
                                planet_dist_fn_t dist_fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"%s\",\"library\":\"libnova\",", experiment);
    printf("\"model\":\"%s\",", model);
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        struct ln_equ_posn posn;
        equ_fn(jd_tt, &posn);

        double ra_rad = posn.ra * (M_PI / 180.0);
        double dec_rad = posn.dec * (M_PI / 180.0);
        double dist_au = dist_fn(jd_tt);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra_rad, dec_rad, dist_au);
    }
    printf("\n]}\n");
}

/* ------------------------------------------------------------------ */
/* Geometric ephemeris runners                                         */
/*                                                                     */
/* These honour the LAB_LANE=geometric contract: no nutation,          */
/* no aberration, no light-time correction. They use libnova's         */
/* rectangular helio/geo helpers, which return AU vectors aligned      */
/* with equatorial J2000 (≈ICRF) via the J2000 obliquity rotation in  */
/* ln_get_rect_from_helio (sin_e=0.397777156, cos_e=0.917482062).      */
/* Output frame: equatorial J2000 / ICRF, comparable directly to JPL   */
/* Horizons VECTORS (VEC_CORR=NONE, REF_PLANE=FRAME, REF_SYSTEM=ICRF). */
/* ------------------------------------------------------------------ */

static void rect_to_radec_au(double X, double Y, double Z,
                             double *ra_rad, double *dec_rad, double *dist_au) {
    double r = sqrt(X * X + Y * Y + Z * Z);
    double ra = atan2(Y, X);
    if (ra < 0.0) ra += 2.0 * M_PI;
    *ra_rad = ra;
    *dec_rad = asin(Z / r);
    *dist_au = r;
}

void run_solar_position_geometric(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"solar_position\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_VSOP87_geometric\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        struct ln_rect_posn rect;
        ln_get_solar_geo_coords(jd_tt, &rect);
        double ra, dec, dist;
        rect_to_radec_au(rect.X, rect.Y, rect.Z, &ra, &dec, &dist);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra, dec, dist);
    }
    printf("\n]}\n");
}

/* J2000 obliquity (degrees → sin/cos) for the ecliptic→equatorial rotation
 * applied to the lunar geocentric vector, which comes out of libnova in the
 * inertial mean ecliptic and equinox of J2000. */
#define LN_J2000_SIN_E 0.397777156
#define LN_J2000_COS_E 0.917482062

void run_lunar_position_geometric(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"lunar_position\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_ELP2000_geometric\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        struct ln_rect_posn ecl;
        /* precision=0 → highest accuracy ELP 2000-82B series */
        ln_get_lunar_geo_posn(jd_tt, &ecl, 0.0);
        /* Rotate ecliptic-J2000 → equatorial-J2000 (≈ICRF). */
        double X = ecl.X;
        double Y = ecl.Y * LN_J2000_COS_E - ecl.Z * LN_J2000_SIN_E;
        double Z = ecl.Y * LN_J2000_SIN_E + ecl.Z * LN_J2000_COS_E;
        /* Lunar coords are in km already, so keep dist_km. */
        double r_km = sqrt(X * X + Y * Y + Z * Z);
        double ra = atan2(Y, X); if (ra < 0.0) ra += 2.0 * M_PI;
        double dec = asin(Z / r_km);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_km\":%.17e}", ra, dec, r_km);
    }
    printf("\n]}\n");
}

void run_planet_position_geometric(const char *experiment,
                                          const char *model,
                                          planet_rect_helio_fn_t rect_helio_fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"%s\",\"library\":\"libnova\",", experiment);
    printf("\"model\":\"%s\",", model);
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt;
        if (scanf("%lf", &jd_tt) != 1) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        /* Heliocentric planet & Earth, both in equatorial-J2000 AU rect coords.
         * Geocentric body = planet − Earth (no light-time, no aberration). */
        struct ln_rect_posn p, e;
        rect_helio_fn(jd_tt, &p);
        ln_get_earth_rect_helio(jd_tt, &e);
        double ra, dec, dist;
        rect_to_radec_au(p.X - e.X, p.Y - e.Y, p.Z - e.Z, &ra, &dec, &dist);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,", jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,\"dist_au\":%.17e}", ra, dec, dist);
    }
    printf("\n]}\n");
}

void run_solar_position_geometric_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) { fprintf(stderr, "bad input line %d\n", i); exit(1); }
    }
    for (int i = 0; i < n && i < 100; i++) {
        struct ln_rect_posn r;
        ln_get_solar_geo_coords(jds[i], &r);
        (void)r;
    }
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_rect_posn r;
        ln_get_solar_geo_coords(jds[i], &r);
        sink += r.X + r.Y + r.Z;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;
    printf("{\"experiment\":\"solar_position_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(jds);
}

void run_lunar_position_geometric_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) { fprintf(stderr, "bad input line %d\n", i); exit(1); }
    }
    for (int i = 0; i < n && i < 100; i++) {
        struct ln_rect_posn r;
        ln_get_lunar_geo_posn(jds[i], &r, 0.0);
        (void)r;
    }
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_rect_posn r;
        ln_get_lunar_geo_posn(jds[i], &r, 0.0);
        sink += r.X + r.Y + r.Z;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;
    printf("{\"experiment\":\"lunar_position_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(jds);
}

void run_planet_position_geometric_perf(const char *experiment,
                                               planet_rect_helio_fn_t rect_helio_fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) { fprintf(stderr, "bad input line %d\n", i); exit(1); }
    }
    for (int i = 0; i < n && i < 100; i++) {
        struct ln_rect_posn p, e;
        rect_helio_fn(jds[i], &p);
        ln_get_earth_rect_helio(jds[i], &e);
        (void)p; (void)e;
    }
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_rect_posn p, e;
        rect_helio_fn(jds[i], &p);
        ln_get_earth_rect_helio(jds[i], &e);
        sink += (p.X - e.X) + (p.Y - e.Y) + (p.Z - e.Z);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;
    printf("{\"experiment\":\"%s_perf\",\"library\":\"libnova\",", experiment);
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(jds);
}

/* Lane selector: LAB_LANE=geometric or LAB_LANE=geometric_vector routes to
 * the helio/geo rectangular path.  Anything else (unset, "apparent", legacy)
 * routes to the equ_coords apparent path.
 *
 * The orchestrator sends "geometric_vector" (the canonical lane token);
 * "geometric" is kept for backwards-compat with local invocations. */
int lane_is_geometric(void) {
    const char *lane = getenv("LAB_LANE");
    if (lane == NULL) return 0;
    return strcmp(lane, "geometric") == 0 || strcmp(lane, "geometric_vector") == 0;
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

    /* Warm-up: match functional scope (RA/Dec plus distance). */
    for (int i = 0; i < n && i < 100; i++) {
        struct ln_equ_posn equ;
        ln_get_solar_equ_coords(jds[i], &equ);
        double dist_au = ln_get_earth_solar_dist(jds[i]);
        (void)dist_au;
    }

    /* Timed run — perf contract: compute RA + Dec + distance */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn equ;
        ln_get_solar_equ_coords(jds[i], &equ);
        double dist_au = ln_get_earth_solar_dist(jds[i]);
        sink += equ.ra + equ.dec + dist_au;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"solar_position_perf\",\"library\":\"libnova\",");
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

    /* Warm-up: match functional scope (RA/Dec plus distance). */
    for (int i = 0; i < n && i < 100; i++) {
        struct ln_equ_posn equ;
        ln_get_lunar_equ_coords(jds[i], &equ);
        double dist_km = ln_get_lunar_earth_dist(jds[i]);
        (void)dist_km;
    }

    /* Timed run — perf contract: compute RA + Dec + distance */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn equ;
        ln_get_lunar_equ_coords(jds[i], &equ);
        double dist_km = ln_get_lunar_earth_dist(jds[i]);
        sink += equ.ra + equ.dec + dist_km;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"lunar_position_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
}

void run_planet_position_perf(const char *experiment,
                                     planet_equ_fn_t equ_fn,
                                     planet_dist_fn_t dist_fn) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jds = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf", &jds[i]) != 1) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    for (int i = 0; i < n && i < 100; i++) {
        struct ln_equ_posn equ;
        equ_fn(jds[i], &equ);
        double dist_au = dist_fn(jds[i]);
        (void)dist_au;
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn equ;
        equ_fn(jds[i], &equ);
        double dist_au = dist_fn(jds[i]);
        sink += equ.ra + equ.dec + dist_au;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"%s_perf\",\"library\":\"libnova\",", experiment);
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
}
