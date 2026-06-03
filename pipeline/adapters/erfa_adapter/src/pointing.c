#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: equ_horizontal                                          */
/* Equatorial (RA/Dec) → Horizontal (Az/Alt) via GAST + eraHd2ae       */
/* Input per line: jd_ut1 jd_tt ra_rad dec_rad obs_lon_rad obs_lat_rad */
/* ------------------------------------------------------------------ */

void run_equ_horizontal(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"equ_horizontal\",\"library\":\"erfa\",");
    printf("\"model\":\"eraHd2ae_GAST\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt, ra_rad, dec_rad, obs_lon, obs_lat;
        if (scanf("%lf %lf %lf %lf %lf %lf", &jd_ut1, &jd_tt, &ra_rad, &dec_rad,
                  &obs_lon, &obs_lat) != 6) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double ut1_hi = 2451545.0, ut1_lo = jd_ut1 - 2451545.0;
        double tt_hi  = 2451545.0, tt_lo  = jd_tt  - 2451545.0;

        double gast = eraGst06a(ut1_hi, ut1_lo, tt_hi, tt_lo);
        double last = gast + obs_lon;
        double ha   = last - ra_rad;

        double az, alt;
        eraHd2ae(ha, dec_rad, obs_lat, &az, &alt);

        /* Closure */
        double ha_back, dec_back;
        eraAe2hd(az, alt, obs_lat, &ha_back, &dec_back);
        double ra_back = last - ha_back;
        double v_in[3]  = { cos(dec_rad)*cos(ra_rad), cos(dec_rad)*sin(ra_rad), sin(dec_rad) };
        double v_bk[3]  = { cos(dec_back)*cos(ra_back), cos(dec_back)*sin(ra_back), sin(dec_back) };
        double closure_rad = ang_sep(v_in, v_bk);

        if (i > 0) printf(",\n");
        printf("{\"jd_ut1\":%.15f,\"jd_tt\":%.15f,", jd_ut1, jd_tt);
        printf("\"ra_rad\":%.17e,\"dec_rad\":%.17e,", ra_rad, dec_rad);
        printf("\"obs_lon_rad\":%.17e,\"obs_lat_rad\":%.17e,", obs_lon, obs_lat);
        printf("\"az_rad\":%.17e,\"alt_rad\":%.17e,", az, alt);
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

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double jd_ut1 = params[6*i];
        double jd_tt = params[6*i+1];
        double ra = params[6*i+2];
        double dec = params[6*i+3];
        double lon = params[6*i+4];
        double lat = params[6*i+5];

        double gast = eraGst06a(2451545.0, jd_ut1 - 2451545.0,
                                2451545.0, jd_tt - 2451545.0);
        double ha = normalize_angle(gast + lon - ra);
        double az, alt;
        eraHd2ae(ha, dec, lat, &az, &alt);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double jd_ut1 = params[6*i];
        double jd_tt = params[6*i+1];
        double ra = params[6*i+2];
        double dec = params[6*i+3];
        double lon = params[6*i+4];
        double lat = params[6*i+5];

        double gast = eraGst06a(2451545.0, jd_ut1 - 2451545.0,
                                2451545.0, jd_tt - 2451545.0);
        double ha = normalize_angle(gast + lon - ra);
        double az, alt;
        eraHd2ae(ha, dec, lat, &az, &alt);
        sink += az;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"equ_horizontal_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(params);
}
/* ------------------------------------------------------------------ */
/* Experiment: horiz_to_equ                                            */
/* Horizontal (Az/Alt) → Equatorial (RA/Dec) via eraAe2hd + GAST      */
/* Input: jd_ut1 jd_tt az_rad alt_rad obs_lon_rad obs_lat_rad         */
/* ------------------------------------------------------------------ */

void run_horiz_to_equ(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"horiz_to_equ\",\"library\":\"erfa\",");
    printf("\"model\":\"eraAe2hd_GAST\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt, az_rad, alt_rad, obs_lon, obs_lat;
        if (scanf("%lf %lf %lf %lf %lf %lf", &jd_ut1, &jd_tt, &az_rad, &alt_rad,
                  &obs_lon, &obs_lat) != 6) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double ut1_hi = 2451545.0, ut1_lo = jd_ut1 - 2451545.0;
        double tt_hi  = 2451545.0, tt_lo  = jd_tt  - 2451545.0;

        double gast = eraGst06a(ut1_hi, ut1_lo, tt_hi, tt_lo);
        double last = gast + obs_lon;

        /* Az/Alt → HA/Dec */
        double ha, dec;
        eraAe2hd(az_rad, alt_rad, obs_lat, &ha, &dec);
        double ra = normalize_angle(last - ha);

        /* Closure: RA/Dec → Az/Alt → RA/Dec */
        double ha2 = last - ra;
        double az2, alt2;
        eraHd2ae(ha2, dec, obs_lat, &az2, &alt2);
        double ha_back, dec_back;
        eraAe2hd(az2, alt2, obs_lat, &ha_back, &dec_back);
        double ra_back = normalize_angle(last - ha_back);

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

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double jd_ut1 = params[6*i], jd_tt = params[6*i+1];
        double az = params[6*i+2], alt = params[6*i+3];
        double lon = params[6*i+4], lat = params[6*i+5];
        double gast = eraGst06a(2451545.0, jd_ut1 - 2451545.0, 2451545.0, jd_tt - 2451545.0);
        double ha, dec;
        eraAe2hd(az, alt, lat, &ha, &dec);
        (void)ha; (void)dec; (void)gast; (void)lon;
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double jd_ut1 = params[6*i], jd_tt = params[6*i+1];
        double az = params[6*i+2], alt = params[6*i+3];
        double lon = params[6*i+4], lat = params[6*i+5];
        double gast = eraGst06a(2451545.0, jd_ut1 - 2451545.0, 2451545.0, jd_tt - 2451545.0);
        double last = gast + lon;
        double ha, dec;
        eraAe2hd(az, alt, lat, &ha, &dec);
        double ra = normalize_angle(last - ha);
        sink += ra + dec;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"horiz_to_equ_perf\",\"library\":\"erfa\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(params);
}
