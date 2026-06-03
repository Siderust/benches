#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: equ_horizontal                                          */
/* Equatorial → Horizontal via libnova                                 */
/* libnova azimuth: 0°=South, increasing westward → convert to         */
/* 0°=North, increasing eastward to match ERFA convention.             */
/* Input per line: jd_ut1 jd_tt ra_rad dec_rad obs_lon_rad obs_lat_rad */
/* ------------------------------------------------------------------ */

void run_equ_horizontal(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"equ_horizontal\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_transform\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt, ra_rad, dec_rad, obs_lon, obs_lat;
        if (scanf("%lf %lf %lf %lf %lf %lf", &jd_ut1, &jd_tt, &ra_rad, &dec_rad,
                  &obs_lon, &obs_lat) != 6) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        double ra_deg  = ra_rad  * (180.0 / M_PI);
        double dec_deg = dec_rad * (180.0 / M_PI);
        double lon_deg = obs_lon * (180.0 / M_PI);
        double lat_deg = obs_lat * (180.0 / M_PI);

        struct ln_equ_posn equ = { .ra = ra_deg, .dec = dec_deg };
        struct ln_lnlat_posn observer = { .lng = lon_deg, .lat = lat_deg };
        struct ln_hrz_posn hrz;
        ln_get_hrz_from_equ(&equ, &observer, jd_ut1, &hrz);

        /* libnova: az 0=South, increasing toward West (CW from above).
         * ERFA:    az 0=North, increasing toward East (CW from above).
         * Convert: az_erfa = (az_libnova + 180°) mod 360° */
        double az_erfa_deg = fmod(hrz.az + 180.0, 360.0);
        double az_rad = az_erfa_deg * (M_PI / 180.0);
        double alt_rad = hrz.alt * (M_PI / 180.0);

        /* Closure via reverse */
        struct ln_hrz_posn hrz2 = { .az = hrz.az, .alt = hrz.alt };
        struct ln_equ_posn equ_back;
        ln_get_equ_from_hrz(&hrz2, &observer, jd_ut1, &equ_back);

        double ra_back  = equ_back.ra  * (M_PI / 180.0);
        double dec_back = equ_back.dec * (M_PI / 180.0);
        double v_in[3]  = { cos(dec_rad)*cos(ra_rad), cos(dec_rad)*sin(ra_rad), sin(dec_rad) };
        double v_bk[3]  = { cos(dec_back)*cos(ra_back), cos(dec_back)*sin(ra_back), sin(dec_back) };
        double closure_rad = ang_sep(v_in, v_bk);

        if (i > 0) printf(",\n");
        printf("{\"jd_ut1\":%.15f,\"jd_tt\":%.15f,", jd_ut1, jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,", ra_rad, dec_rad);
        printf("\"obs_lon_rad\":%.17e,\"obs_lat_rad\":%.17e,", obs_lon, obs_lat);
        printf("\"az_rad\":%.17e,\"alt_rad\":%.17e,", az_rad, alt_rad);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_equ_horizontal_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *params = malloc(n * 6 * sizeof(double));

    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf %lf %lf",
                  &params[6*i], &params[6*i+1], &params[6*i+2],
                  &params[6*i+3], &params[6*i+4], &params[6*i+5]) != 6) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Pre-convert to libnova degree-based coordinates outside timing. */
    double *params_deg = malloc(n * 5 * sizeof(double));
    for (int i = 0; i < n; i++) {
        params_deg[5*i] = params[6*i];  /* jd_ut1 */
        params_deg[5*i+1] = params[6*i+2] * (180.0 / M_PI); /* ra */
        params_deg[5*i+2] = params[6*i+3] * (180.0 / M_PI); /* dec */
        params_deg[5*i+3] = params[6*i+4] * (180.0 / M_PI); /* lon */
        params_deg[5*i+4] = params[6*i+5] * (180.0 / M_PI); /* lat */
    }

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double jd_ut1 = params_deg[5*i];
        double ra = params_deg[5*i+1];
        double dec = params_deg[5*i+2];
        double lon = params_deg[5*i+3];
        double lat = params_deg[5*i+4];

        struct ln_equ_posn object = { ra, dec };
        struct ln_lnlat_posn observer = { lon, lat };
        struct ln_hrz_posn hrz;
        ln_get_hrz_from_equ(&object, &observer, jd_ut1, &hrz);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double jd_ut1 = params_deg[5*i];
        double ra = params_deg[5*i+1];
        double dec = params_deg[5*i+2];
        double lon = params_deg[5*i+3];
        double lat = params_deg[5*i+4];

        struct ln_equ_posn object = { ra, dec };
        struct ln_lnlat_posn observer = { lon, lat };
        struct ln_hrz_posn hrz;
        ln_get_hrz_from_equ(&object, &observer, jd_ut1, &hrz);
        sink += hrz.az;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"equ_horizontal_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(params);
    free(params_deg);
}

/* ------------------------------------------------------------------ */
/* Experiment: horiz_to_equ                                            */
/* Horizontal → Equatorial via ln_get_equ_from_hrz                     */
/* Input: jd_ut1 jd_tt az_rad alt_rad obs_lon_rad obs_lat_rad         */
/* ------------------------------------------------------------------ */

void run_horiz_to_equ(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"horiz_to_equ\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_transform\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt, az_rad, alt_rad, obs_lon, obs_lat;
        if (scanf("%lf %lf %lf %lf %lf %lf", &jd_ut1, &jd_tt, &az_rad, &alt_rad,
                  &obs_lon, &obs_lat) != 6) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        /* Convert ERFA convention (az: 0=N, CW) → libnova (az: 0=S, CW):
         * az_libnova = (az_erfa - 180) mod 360 */
        double az_deg_ln = fmod((az_rad * (180.0 / M_PI)) - 180.0 + 360.0, 360.0);
        double alt_deg = alt_rad * (180.0 / M_PI);
        double lon_deg = obs_lon * (180.0 / M_PI);
        double lat_deg = obs_lat * (180.0 / M_PI);

        struct ln_hrz_posn hrz = { .az = az_deg_ln, .alt = alt_deg };
        struct ln_lnlat_posn observer = { .lng = lon_deg, .lat = lat_deg };
        struct ln_equ_posn equ;
        ln_get_equ_from_hrz(&hrz, &observer, jd_ut1, &equ);

        double ra  = equ.ra  * (M_PI / 180.0);
        double dec = equ.dec * (M_PI / 180.0);

        /* Closure: equ → hrz → equ */
        struct ln_hrz_posn hrz2;
        ln_get_hrz_from_equ(&equ, &observer, jd_ut1, &hrz2);
        struct ln_equ_posn equ_back;
        ln_get_equ_from_hrz(&hrz2, &observer, jd_ut1, &equ_back);

        double ra_back  = equ_back.ra  * (M_PI / 180.0);
        double dec_back = equ_back.dec * (M_PI / 180.0);
        double v_in[3]  = { cos(dec)*cos(ra), cos(dec)*sin(ra), sin(dec) };
        double v_bk[3]  = { cos(dec_back)*cos(ra_back), cos(dec_back)*sin(ra_back), sin(dec_back) };
        double closure_rad = ang_sep(v_in, v_bk);

        if (i > 0) printf(",\n");
        printf("{\"jd_ut1\":%.15f,\"jd_tt\":%.15f,", jd_ut1, jd_tt);
        printf("\"az_rad\":%.17e,\"alt_rad\":%.17e,", az_rad, alt_rad);
        printf("\"obs_lon_rad\":%.17e,\"obs_lat_rad\":%.17e,", obs_lon, obs_lat);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,", ra, dec);
        printf("\"closure_rad\":%.17e}", closure_rad);
    }
    printf("\n]}\n");
}

void run_horiz_to_equ_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *params = malloc(n * 6 * sizeof(double));
    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf %lf %lf %lf %lf",
                  &params[6*i], &params[6*i+1], &params[6*i+2],
                  &params[6*i+3], &params[6*i+4], &params[6*i+5]) != 6) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
    }

    /* Pre-convert to libnova degree-based coordinates */
    double *p_deg = malloc(n * 5 * sizeof(double));
    for (int i = 0; i < n; i++) {
        p_deg[5*i]   = params[6*i]; /* jd_ut1 */
        double az_deg_ln = fmod((params[6*i+2] * (180.0 / M_PI)) - 180.0 + 360.0, 360.0);
        p_deg[5*i+1] = az_deg_ln;
        p_deg[5*i+2] = params[6*i+3] * (180.0 / M_PI); /* alt */
        p_deg[5*i+3] = params[6*i+4] * (180.0 / M_PI); /* lon */
        p_deg[5*i+4] = params[6*i+5] * (180.0 / M_PI); /* lat */
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_hrz_posn hrz = { p_deg[5*i+1], p_deg[5*i+2] };
        struct ln_lnlat_posn obs = { p_deg[5*i+3], p_deg[5*i+4] };
        struct ln_equ_posn equ;
        ln_get_equ_from_hrz(&hrz, &obs, p_deg[5*i], &equ);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_hrz_posn hrz = { p_deg[5*i+1], p_deg[5*i+2] };
        struct ln_lnlat_posn obs = { p_deg[5*i+3], p_deg[5*i+4] };
        struct ln_equ_posn equ;
        ln_get_equ_from_hrz(&hrz, &obs, p_deg[5*i], &equ);
        sink += equ.ra + equ.dec;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"horiz_to_equ_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(params); free(p_deg);
}
