#include "common.h"

/* ICRS/J2000 equatorial (input RA/Dec) → mean equator of date → ecliptic of date. */
static void libnova_icrs_to_ecl_of_date(
    double jd_tt,
    double ra_j2000_deg,
    double dec_j2000_deg,
    struct ln_lnlat_posn *ecl_out)
{
    struct ln_equ_posn equ_j2000 = { .ra = ra_j2000_deg, .dec = dec_j2000_deg };
    struct ln_equ_posn equ_date;
    ln_get_equ_prec(&equ_j2000, jd_tt, &equ_date);
    ln_get_ecl_from_equ(&equ_date, jd_tt, ecl_out);
}

/* Ecliptic of date → mean equator of date → ICRS/J2000 equatorial. */
static void libnova_ecl_of_date_to_icrs(
    double jd_tt,
    const struct ln_lnlat_posn *ecl,
    struct ln_equ_posn *equ_j2000_out)
{
    struct ln_equ_posn equ_date;
    struct ln_lnlat_posn ecl_mut = { .lng = ecl->lng, .lat = ecl->lat };
    ln_get_equ_from_ecl(&ecl_mut, jd_tt, &equ_date);
    ln_get_equ_prec2(&equ_date, jd_tt, JD2000, equ_j2000_out);
}

/* ------------------------------------------------------------------ */
/* Experiment: equ_ecl                                                 */
/* Equatorial ↔ Ecliptic via libnova transform API                     */
/* libnova uses degrees: RA in hours→deg, Dec in deg, lon/lat in deg   */
/* Input per line: jd_tt  ra_rad  dec_rad                              */
/* ------------------------------------------------------------------ */

void run_equ_ecl(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"equ_ecl\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_icrs_to_ecl_of_date\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, ra_rad, dec_rad;
        if (scanf("%lf %lf %lf", &jd_tt, &ra_rad, &dec_rad) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }

        /* Input is ICRS/J2000 RA/Dec (radians); libnova uses degrees. */
        double ra_deg  = ra_rad  * (180.0 / M_PI);
        double dec_deg = dec_rad * (180.0 / M_PI);

        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jd_tt, ra_deg, dec_deg, &ecl);

        double ecl_lon = ecl.lng * (M_PI / 180.0);
        double ecl_lat = ecl.lat * (M_PI / 180.0);

        /* Closure: ecliptic of date → ICRS/J2000 equatorial */
        struct ln_equ_posn equ_j2000_back;
        libnova_ecl_of_date_to_icrs(jd_tt, &ecl, &equ_j2000_back);

        double ra_back  = equ_j2000_back.ra  * (M_PI / 180.0);
        double dec_back = equ_j2000_back.dec * (M_PI / 180.0);

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

    /* Pre-convert to libnova API units outside timed loops for fairness. */
    double *ras_deg = malloc(n * sizeof(double));
    double *decs_deg = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        ras_deg[i] = ras[i] * (180.0 / M_PI);
        decs_deg[i] = decs[i] * (180.0 / M_PI);
    }

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jds[i], ras_deg[i], decs_deg[i], &ecl);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jds[i], ras_deg[i], decs_deg[i], &ecl);
        sink += ecl.lng;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    double per_op_ns = elapsed_ns / n;

    printf("{\"experiment\":\"equ_ecl_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, per_op_ns);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);

    free(jds);
    free(ras);
    free(decs);
    free(ras_deg);
    free(decs_deg);
}

/* ------------------------------------------------------------------ */
/* Experiment: icrs_ecl_j2000                                          */
/* Equatorial → Ecliptic via ln_get_ecl_from_equ at J2000              */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_icrs_ecl_j2000(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"icrs_ecl_j2000\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_transform_J2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double vin[3] = {vx, vy, vz};
        normalize3(vin);

        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);

        struct ln_equ_posn equ = { .ra = ra_deg, .dec = dec_deg };
        struct ln_lnlat_posn ecl;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl);

        double ecl_lon = ecl.lng * (M_PI / 180.0);
        double ecl_lat = ecl.lat * (M_PI / 180.0);

        /* Build output unit vector in ecliptic frame */
        double vout[3] = { cos(ecl_lat)*cos(ecl_lon), cos(ecl_lat)*sin(ecl_lon), sin(ecl_lat) };
        normalize3(vout);

        /* Closure */
        struct ln_equ_posn equ_back;
        ln_get_equ_from_ecl(&ecl, JD2000, &equ_back);
        double vback[3];
        radec_to_cart(equ_back.ra, equ_back.dec, vback);
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

    double *ras_deg = malloc(n * sizeof(double));
    double *decs_deg = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        cart_to_radec(vin, &ras_deg[i], &decs_deg[i]);
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_equ_posn equ = { ras_deg[i], decs_deg[i] };
        struct ln_lnlat_posn ecl;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn equ = { ras_deg[i], decs_deg[i] };
        struct ln_lnlat_posn ecl;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl);
        sink += ecl.lng;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"icrs_ecl_j2000_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(ras_deg); free(decs_deg);
}

/* ------------------------------------------------------------------ */
/* Experiment: icrs_ecl_tod                                            */
/* Equatorial → Ecliptic of date via ln_get_ecl_from_equ               */
/* Input per line: jd_tt ra_rad dec_rad                                */
/* ------------------------------------------------------------------ */

void run_icrs_ecl_tod(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"icrs_ecl_tod\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_icrs_to_ecl_of_date\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, ra_rad, dec_rad;
        if (scanf("%lf %lf %lf", &jd_tt, &ra_rad, &dec_rad) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        double ra_deg  = ra_rad  * (180.0 / M_PI);
        double dec_deg = dec_rad * (180.0 / M_PI);

        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jd_tt, ra_deg, dec_deg, &ecl);

        double ecl_lon = ecl.lng * (M_PI / 180.0);
        double ecl_lat = ecl.lat * (M_PI / 180.0);

        /* Closure: ecliptic of date → ICRS/J2000 */
        struct ln_equ_posn equ_j2000_back;
        libnova_ecl_of_date_to_icrs(jd_tt, &ecl, &equ_j2000_back);
        double ra_back  = equ_j2000_back.ra  * (M_PI / 180.0);
        double dec_back = equ_j2000_back.dec * (M_PI / 180.0);
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
    double *ras_deg = malloc(n * sizeof(double));
    double *decs_deg = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt, ra_rad, dec_rad;
        if (scanf("%lf %lf %lf", &jd_tt, &ra_rad, &dec_rad) != 3) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        jds[i] = jd_tt;
        ras_deg[i] = ra_rad * (180.0 / M_PI);
        decs_deg[i] = dec_rad * (180.0 / M_PI);
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jds[i], ras_deg[i], decs_deg[i], &ecl);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_lnlat_posn ecl;
        libnova_icrs_to_ecl_of_date(jds[i], ras_deg[i], decs_deg[i], &ecl);
        sink += ecl.lng + ecl.lat;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    printf("{\"experiment\":\"icrs_ecl_tod_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,", n, elapsed_ns, elapsed_ns / n);
    printf("\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           (double)n / (elapsed_ns * 1e-9), sink);
    free(jds); free(ras_deg); free(decs_deg);
}

/* --- inv_icrs_ecl_j2000: EclMeanJ2000 → ICRS (≈EqJ2000) via ln_get_equ_from_ecl at J2000 --- */
void run_inv_icrs_ecl_j2000(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_icrs_ecl_j2000\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_inv_ecl_j2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        /* Input is ecliptic direction vector → convert to lon/lat */
        double lon_deg, lat_deg;
        cart_to_radec(vin, &lon_deg, &lat_deg); /* same math for spherical coords */
        struct ln_lnlat_posn ecl = { lon_deg, lat_deg };
        struct ln_equ_posn equ;
        ln_get_equ_from_ecl(&ecl, JD2000, &equ);
        double vout[3]; radec_to_cart(equ.ra, equ.dec, vout); normalize3(vout);
        /* Closure: convert back */
        struct ln_lnlat_posn ecl_back;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl_back);
        double vback[3]; radec_to_cart(ecl_back.lng, ecl_back.lat, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_icrs_ecl_j2000_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *lons=malloc(n*sizeof(double)), *lats=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&lons[i],&lats[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e, JD2000, &q);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e, JD2000, &q);
        sink+=q.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    printf("{\"experiment\":\"inv_icrs_ecl_j2000_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           n, ns, ns/n, (double)n/(ns*1e-9), sink);
    free(lons); free(lats);
}

/* --- obliquity: EclMeanJ2000 → EqMeanJ2000 via ln_get_equ_from_ecl at J2000 --- */
void run_obliquity(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"obliquity\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_obliquity_j2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double lon_deg, lat_deg;
        cart_to_radec(vin, &lon_deg, &lat_deg);
        struct ln_lnlat_posn ecl = { lon_deg, lat_deg };
        struct ln_equ_posn equ;
        ln_get_equ_from_ecl(&ecl, JD2000, &equ);
        double vout[3]; radec_to_cart(equ.ra, equ.dec, vout); normalize3(vout);
        struct ln_lnlat_posn ecl_back;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl_back);
        double vback[3]; radec_to_cart(ecl_back.lng, ecl_back.lat, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_obliquity_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *lons=malloc(n*sizeof(double)), *lats=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&lons[i],&lats[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e, JD2000, &q);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e, JD2000, &q); sink+=q.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    printf("{\"experiment\":\"obliquity_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           n, ns, ns/n, (double)n/(ns*1e-9), sink);
    free(lons); free(lats);
}

/* --- inv_obliquity: EqMeanJ2000 → EclMeanJ2000 via ln_get_ecl_from_equ at J2000 --- */
void run_inv_obliquity(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_obliquity\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_inv_obliquity_j2000\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);
        struct ln_equ_posn equ = { ra_deg, dec_deg };
        struct ln_lnlat_posn ecl;
        ln_get_ecl_from_equ(&equ, JD2000, &ecl);
        double ecl_lon = ecl.lng * (M_PI/180.0);
        double ecl_lat = ecl.lat * (M_PI/180.0);
        double vout[3] = { cos(ecl_lat)*cos(ecl_lon), cos(ecl_lat)*sin(ecl_lon), sin(ecl_lat) };
        normalize3(vout);
        /* Closure */
        struct ln_equ_posn equ_back;
        ln_get_equ_from_ecl(&ecl, JD2000, &equ_back);
        double vback[3]; radec_to_cart(equ_back.ra, equ_back.dec, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_obliquity_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *ras=malloc(n*sizeof(double)), *decs=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&ras[i],&decs[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_equ_posn e={ras[i],decs[i]}; struct ln_lnlat_posn q;
        ln_get_ecl_from_equ(&e, JD2000, &q);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_equ_posn e={ras[i],decs[i]}; struct ln_lnlat_posn q;
        ln_get_ecl_from_equ(&e, JD2000, &q); sink+=q.lng;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    printf("{\"experiment\":\"inv_obliquity_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           n, ns, ns/n, (double)n/(ns*1e-9), sink);
    free(ras); free(decs);
}

/* --- inv_icrs_ecl_tod: EclTrueOfDate → ICRS via ecl→eq(date) then prec→J2000 --- */
void run_inv_icrs_ecl_tod(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_icrs_ecl_tod\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_inv_ecl_tod\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double lon_deg, lat_deg;
        cart_to_radec(vin, &lon_deg, &lat_deg);
        struct ln_lnlat_posn ecl = { lon_deg, lat_deg };
        struct ln_equ_posn equ_date;
        ln_get_equ_from_ecl(&ecl, jd_tt, &equ_date);
        /* Precess back to J2000 (≈ICRS) */
        struct ln_equ_posn equ_j2000;
        ln_get_equ_prec2(&equ_date, jd_tt, JD2000, &equ_j2000);
        double vout[3]; radec_to_cart(equ_j2000.ra, equ_j2000.dec, vout); normalize3(vout);
        /* Closure */
        struct ln_equ_posn fwd_date;
        ln_get_equ_prec(&equ_j2000, jd_tt, &fwd_date);
        struct ln_lnlat_posn ecl_back;
        ln_get_ecl_from_equ(&fwd_date, jd_tt, &ecl_back);
        double vback[3];
        double blon=ecl_back.lng*(M_PI/180.0), blat=ecl_back.lat*(M_PI/180.0);
        vback[0]=cos(blat)*cos(blon); vback[1]=cos(blat)*sin(blon); vback[2]=sin(blat);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_icrs_ecl_tod_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds=malloc(n*sizeof(double)), *lons=malloc(n*sizeof(double)), *lats=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        jds[i]=jd; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&lons[i],&lats[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q, j;
        ln_get_equ_from_ecl(&e,jds[i],&q); ln_get_equ_prec2(&q,jds[i],JD2000,&j);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q, j;
        ln_get_equ_from_ecl(&e,jds[i],&q); ln_get_equ_prec2(&q,jds[i],JD2000,&j); sink+=j.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    printf("{\"experiment\":\"inv_icrs_ecl_tod_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           n, ns, ns/n, (double)n/(ns*1e-9), sink);
    free(jds); free(lons); free(lats);
}

/* --- inv_equ_ecl: EclTrueOfDate → EqMeanOfDate via ln_get_equ_from_ecl(date) --- */
void run_inv_equ_ecl(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_equ_ecl\",\"library\":\"libnova\",");
    printf("\"model\":\"libnova_inv_equ_ecl\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double lon_deg, lat_deg;
        cart_to_radec(vin, &lon_deg, &lat_deg);
        struct ln_lnlat_posn ecl = { lon_deg, lat_deg };
        struct ln_equ_posn equ_date;
        ln_get_equ_from_ecl(&ecl, jd_tt, &equ_date);
        double vout[3]; radec_to_cart(equ_date.ra, equ_date.dec, vout); normalize3(vout);
        /* Closure */
        struct ln_lnlat_posn ecl_back;
        ln_get_ecl_from_equ(&equ_date, jd_tt, &ecl_back);
        double vback[3];
        double blon=ecl_back.lng*(M_PI/180.0), blat=ecl_back.lat*(M_PI/180.0);
        vback[0]=cos(blat)*cos(blon); vback[1]=cos(blat)*sin(blon); vback[2]=sin(blat);
        normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_equ_ecl_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds=malloc(n*sizeof(double)), *lons=malloc(n*sizeof(double)), *lats=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        jds[i]=jd; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&lons[i],&lats[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e,jds[i],&q);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_lnlat_posn e={lons[i],lats[i]}; struct ln_equ_posn q;
        ln_get_equ_from_ecl(&e,jds[i],&q); sink+=q.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    printf("{\"experiment\":\"inv_equ_ecl_perf\",\"library\":\"libnova\",");
    printf("\"count\":%d,\"total_ns\":%.0f,\"per_op_ns\":%.1f,\"throughput_ops_s\":%.0f,\"_sink\":%.17e}\n",
           n, ns, ns/n, (double)n/(ns*1e-9), sink);
    free(jds); free(lons); free(lats);
}
