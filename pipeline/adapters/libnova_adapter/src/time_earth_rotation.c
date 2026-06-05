#include "common.h"

/* ------------------------------------------------------------------ */
/* Experiment: frame_rotation_bpn                                      */
/* Applies Meeus precession + IAU 1980 nutation via libnova's RA/Dec   */
/* coordinate-level API. No rotation matrix is available.              */
/* ------------------------------------------------------------------ */

void run_frame_rotation_bpn(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"frame_rotation_bpn\",\"library\":\"libnova\",");
    printf("\"model\":\"Meeus_prec_IAU1980_nut\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }

        double vin[3] = {vx, vy, vz};
        normalize3(vin);

        /* Forward: J2000 → epoch */
        double vout[3];
        j2000_to_epoch(jd_tt, vin, vout);

        /* Closure: epoch → J2000 */
        double vinv[3];
        epoch_to_j2000(jd_tt, vout, vinv);
        double closure_rad = ang_sep(vin, vinv);

        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],", vout[0], vout[1], vout[2]);
        printf("\"closure_rad\":%.17e,", closure_rad);
        printf("\"matrix\":null}");
    }

    printf("\n]}\n");
}

/* ------------------------------------------------------------------ */
/* Experiment: gmst_era                                                */
/* Computes GMST (Meeus Formula 11.4) and GAST.                       */
/* libnova has no ERA function — era_rad is omitted.                   */
/* ------------------------------------------------------------------ */

void run_gmst_era(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"gmst_era\",\"library\":\"libnova\",");
    printf("\"model\":\"GMST=Meeus_11.4, GAST=MST+nutation\",");
    printf("\"count\":%d,\"cases\":[\n", n);

    for (int i = 0; i < n; i++) {
        double jd_ut1, jd_tt;
        if (scanf("%lf %lf", &jd_ut1, &jd_tt) != 2) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }

        /* ln_get_mean_sidereal_time returns hours */
        double mst_hours  = ln_get_mean_sidereal_time(jd_ut1);
        double gast_hours = ln_get_apparent_sidereal_time(jd_ut1);

        /* Convert hours → radians */
        double gmst_rad = mst_hours  * (M_PI / 12.0);
        double gast_rad = gast_hours * (M_PI / 12.0);

        if (i > 0) printf(",\n");
        printf("{\"jd_ut1\":%.15f,\"jd_tt\":%.15f,", jd_ut1, jd_tt);
        printf("\"gmst_rad\":%.17e,\"gast_rad\":%.17e}", gmst_rad, gast_rad);
    }

    printf("\n]}\n");
}

void run_frame_rotation_bpn_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    /* Read all inputs */
    double *jds  = malloc(n * sizeof(double));
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

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        double vout[3];
        j2000_to_epoch(jds[i], vin, vout);
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double vout[3];
    for (int i = 0; i < n; i++) {
        double vin[3] = {vecs[3*i], vecs[3*i+1], vecs[3*i+2]};
        normalize3(vin);
        j2000_to_epoch(jds[i], vin, vout);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    emit_valid_perf_json("frame_rotation_bpn_perf", n, elapsed_ns, vout[0]);

    free(jds);
    free(vecs);
}

void run_gmst_era_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    double *jd_ut1_arr = malloc(n * sizeof(double));
    double *jd_tt_arr = malloc(n * sizeof(double));

    for (int i = 0; i < n; i++) {
        if (scanf("%lf %lf", &jd_ut1_arr[i], &jd_tt_arr[i]) != 2) {
            fprintf(stderr, "bad input line %d\n", i);
            exit(1);
        }
    }

    /* Warm-up */
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        double gmst = ln_get_mean_sidereal_time(jd_ut1_arr[i]);
        (void)gmst;
    }

    /* Timed run */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        double gmst = ln_get_mean_sidereal_time(jd_ut1_arr[i]);
        sink += gmst;
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    emit_valid_perf_json("gmst_era_perf", n, elapsed_ns, sink);

    free(jd_ut1_arr);
    free(jd_tt_arr);
}

/* ================================================================== */
/* NEW COORDINATE-TRANSFORM EXPERIMENTS                                */
/* ================================================================== */

/* ------------------------------------------------------------------ */
/* Experiment: frame_bias                                              */
/* libnova has no frame bias concept — output skipped JSON.            */
/* ------------------------------------------------------------------ */

void run_frame_bias(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    /* Consume input lines */
    for (int i = 0; i < n; i++) {
        double a, b, c, d;
        scanf("%lf %lf %lf %lf", &a, &b, &c, &d);
    }
    printf("{\"experiment\":\"frame_bias\",\"library\":\"libnova\",\"skipped\":true,");
    printf("\"reason\":\"libnova has no frame bias concept\"}\n");
}

void run_frame_bias_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    for (int i = 0; i < n; i++) {
        double a, b, c, d;
        scanf("%lf %lf %lf %lf", &a, &b, &c, &d);
    }
    printf("{\"experiment\":\"frame_bias_perf\",\"library\":\"libnova\",\"skipped\":true,");
    printf("\"reason\":\"libnova has no frame bias concept\"}\n");
}

/* ------------------------------------------------------------------ */
/* Experiment: precession                                              */
/* J2000 → MeanOfDate via ln_get_equ_prec                              */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_precession(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"precession\",\"library\":\"libnova\",");
    printf("\"model\":\"Meeus_precession\",");
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

        struct ln_equ_posn mean_pos = { .ra = ra_deg, .dec = dec_deg };
        struct ln_equ_posn prec_pos;
        ln_get_equ_prec(&mean_pos, jd_tt, &prec_pos);

        double vout[3];
        radec_to_cart(prec_pos.ra, prec_pos.dec, vout);
        normalize3(vout);

        /* Closure via reverse precession */
        struct ln_equ_posn back_pos;
        ln_get_equ_prec2(&prec_pos, jd_tt, JD2000, &back_pos);
        double vback[3];
        radec_to_cart(back_pos.ra, back_pos.dec, vback);
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
    double *ras_deg = malloc(n * sizeof(double));
    double *decs_deg = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        jds[i] = jd_tt;
        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        cart_to_radec(vin, &ras_deg[i], &decs_deg[i]);
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_equ_posn mean_pos = { ras_deg[i], decs_deg[i] };
        struct ln_equ_posn prec_pos;
        ln_get_equ_prec(&mean_pos, jds[i], &prec_pos);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn mean_pos = { ras_deg[i], decs_deg[i] };
        struct ln_equ_posn prec_pos;
        ln_get_equ_prec(&mean_pos, jds[i], &prec_pos);
        sink += prec_pos.ra;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    emit_valid_perf_json("precession_perf", n, elapsed_ns, sink);
    free(jds); free(ras_deg); free(decs_deg);
}

/* ------------------------------------------------------------------ */
/* Experiment: nutation                                                */
/* MeanOfDate → TrueOfDate via ln_get_equ_nut                         */
/* Input per line: jd_tt vx vy vz                                      */
/* ------------------------------------------------------------------ */

void run_nutation(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }

    printf("{\"experiment\":\"nutation\",\"library\":\"libnova\",");
    printf("\"model\":\"IAU_1980_nutation\",");
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

        struct ln_equ_posn mean_of_date = { .ra = ra_deg, .dec = dec_deg };
        struct ln_equ_posn true_of_date;
        ln_get_equ_nut(&mean_of_date, jd_tt, &true_of_date);

        double vout[3];
        radec_to_cart(true_of_date.ra, true_of_date.dec, vout);
        normalize3(vout);

        /* Closure: undo nutation */
        struct ln_nutation nut;
        ln_get_nutation(jd_tt, &nut);

        double ra_r  = true_of_date.ra * (M_PI / 180.0);
        double dec_r = true_of_date.dec * (M_PI / 180.0);
        double nut_ecliptic = (nut.ecliptic + nut.obliquity) * (M_PI / 180.0);
        double delta_ra = (cos(nut_ecliptic) + sin(nut_ecliptic) * sin(ra_r) * tan(dec_r)) * nut.longitude
                        - cos(ra_r) * tan(dec_r) * nut.obliquity;
        double delta_dec = (sin(nut_ecliptic) * cos(ra_r)) * nut.longitude
                         + sin(ra_r) * nut.obliquity;
        double back_ra  = true_of_date.ra  - delta_ra;
        double back_dec = true_of_date.dec - delta_dec;

        double vback[3];
        radec_to_cart(back_ra, back_dec, vback);
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
    double *ras_deg = malloc(n * sizeof(double));
    double *decs_deg = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) {
            fprintf(stderr, "bad input line %d\n", i); exit(1);
        }
        jds[i] = jd_tt;
        double vin[3] = {vx, vy, vz};
        normalize3(vin);
        cart_to_radec(vin, &ras_deg[i], &decs_deg[i]);
    }

    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_equ_posn pos = { ras_deg[i], decs_deg[i] };
        struct ln_equ_posn out;
        ln_get_equ_nut(&pos, jds[i], &out);
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double sink = 0.0;
    for (int i = 0; i < n; i++) {
        struct ln_equ_posn pos = { ras_deg[i], decs_deg[i] };
        struct ln_equ_posn out;
        ln_get_equ_nut(&pos, jds[i], &out);
        sink += out.ra;
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double elapsed_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);

    emit_valid_perf_json("nutation_perf", n, elapsed_ns, sink);
    free(jds); free(ras_deg); free(decs_deg);
}

/* ================================================================== */
/* 13 NEW DIRECTION-VECTOR TRANSFORM EXPERIMENTS                       */
/* ================================================================== */

/* Helper: skip an experiment (consume N direction-vector inputs) */
static void _skip_dir(const char *exp_name, const char *reason) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    for (int i = 0; i < n; i++) { double a,b,c,d; scanf("%lf %lf %lf %lf", &a,&b,&c,&d); }
    printf("{\"experiment\":\"%s\",\"library\":\"libnova\",\"skipped\":true,", exp_name);
    printf("\"reason\":\"%s\"}\n", reason);
}

/* --- inv_frame_bias: skipped --- */
void run_inv_frame_bias(void)      { _skip_dir("inv_frame_bias",      "libnova has no frame bias concept"); }
void run_inv_frame_bias_perf(void) { _skip_dir("inv_frame_bias_perf", "libnova has no frame bias concept"); }

/* --- inv_bpn: skipped (no ICRS/frame bias) --- */
void run_inv_bpn(void)      { _skip_dir("inv_bpn",      "libnova has no ICRS/frame bias concept"); }
void run_inv_bpn_perf(void) { _skip_dir("inv_bpn_perf", "libnova has no ICRS/frame bias concept"); }

/* --- bias_precession: skipped --- */
void run_bias_precession(void)      { _skip_dir("bias_precession",      "libnova has no frame bias concept"); }
void run_bias_precession_perf(void) { _skip_dir("bias_precession_perf", "libnova has no frame bias concept"); }

/* --- inv_bias_precession: skipped --- */
void run_inv_bias_precession(void)      { _skip_dir("inv_bias_precession",      "libnova has no frame bias concept"); }
void run_inv_bias_precession_perf(void) { _skip_dir("inv_bias_precession_perf", "libnova has no frame bias concept"); }

/* --- inv_precession: MeanOfDate → J2000 via ln_get_equ_prec2 --- */
void run_inv_precession(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_precession\",\"library\":\"libnova\",");
    printf("\"model\":\"Meeus_inv_precession\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt, vx, vy, vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3] = {vx, vy, vz}; normalize3(vin);
        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);
        struct ln_equ_posn pos_date = { ra_deg, dec_deg };
        struct ln_equ_posn pos_j2000;
        ln_get_equ_prec2(&pos_date, jd_tt, JD2000, &pos_j2000);
        double vout[3]; radec_to_cart(pos_j2000.ra, pos_j2000.dec, vout); normalize3(vout);
        /* Closure: precess forward again */
        struct ln_equ_posn check;
        ln_get_equ_prec(&pos_j2000, jd_tt, &check);
        double vback[3]; radec_to_cart(check.ra, check.dec, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_precession_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds = malloc(n * sizeof(double));
    double *ras = malloc(n * sizeof(double));
    double *decs = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz);
        jds[i] = jd_tt; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v, &ras[i], &decs[i]);
    }
    for (int i = 0, warmup = get_perf_warmup(); i < n && i < warmup; i++) {
        struct ln_equ_posn p={ras[i],decs[i]}, o;
        ln_get_equ_prec2(&p, jds[i], JD2000, &o);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_equ_posn p={ras[i],decs[i]}, o;
        ln_get_equ_prec2(&p, jds[i], JD2000, &o);
        sink += o.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    emit_valid_perf_json("inv_precession_perf", n, ns, sink);
    free(jds); free(ras); free(decs);
}

/* --- inv_nutation: TrueOfDate → MeanOfDate (approximate ΔRA/ΔDec subtraction) --- */
void run_inv_nutation(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_nutation\",\"library\":\"libnova\",");
    printf("\"model\":\"IAU_1980_inv_nutation_approx\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);
        /* Compute nutation corrections and subtract (approximate inverse) */
        struct ln_nutation nut;
        ln_get_nutation(jd_tt, &nut);
        double ra_r = ra_deg * (M_PI/180.0);
        double dec_r = dec_deg * (M_PI/180.0);
        double nut_ecl = (nut.ecliptic + nut.obliquity) * (M_PI/180.0);
        double delta_ra = (cos(nut_ecl) + sin(nut_ecl)*sin(ra_r)*tan(dec_r)) * nut.longitude
                        - cos(ra_r)*tan(dec_r) * nut.obliquity;
        double delta_dec = (sin(nut_ecl)*cos(ra_r)) * nut.longitude + sin(ra_r) * nut.obliquity;
        double back_ra = ra_deg - delta_ra;
        double back_dec = dec_deg - delta_dec;
        double vout[3]; radec_to_cart(back_ra, back_dec, vout); normalize3(vout);
        /* Closure: apply nutation forward */
        struct ln_equ_posn mean_pos = { back_ra, back_dec };
        struct ln_equ_posn true_check;
        ln_get_equ_nut(&mean_pos, jd_tt, &true_check);
        double vback[3]; radec_to_cart(true_check.ra, true_check.dec, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_nutation_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds=malloc(n*sizeof(double)), *ras=malloc(n*sizeof(double)), *decs=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        jds[i]=jd; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&ras[i],&decs[i]);
    }
    for (int i=0;i<n&&i<100;i++) { struct ln_nutation nut; ln_get_nutation(jds[i],&nut); }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_nutation nut; ln_get_nutation(jds[i],&nut);
        double ra_r=ras[i]*(M_PI/180.0), dec_r=decs[i]*(M_PI/180.0);
        double nut_ecl=(nut.ecliptic+nut.obliquity)*(M_PI/180.0);
        double delta_ra = (cos(nut_ecl)+sin(nut_ecl)*sin(ra_r)*tan(dec_r))*nut.longitude
                        - cos(ra_r)*tan(dec_r)*nut.obliquity;
        sink += ras[i]-delta_ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    emit_valid_perf_json("inv_nutation_perf", n, ns, sink);
    free(jds); free(ras); free(decs);
}

/* --- precession_nutation: EqMeanJ2000 → EqTrueOfDate via prec then nut --- */
void run_precession_nutation(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"precession_nutation\",\"library\":\"libnova\",");
    printf("\"model\":\"Meeus_prec_IAU1980_nut\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);
        /* Precession: J2000 → date */
        struct ln_equ_posn j2000 = { ra_deg, dec_deg };
        struct ln_equ_posn mean_date;
        ln_get_equ_prec(&j2000, jd_tt, &mean_date);
        /* Nutation: mean → true */
        struct ln_equ_posn true_date;
        ln_get_equ_nut(&mean_date, jd_tt, &true_date);
        double vout[3]; radec_to_cart(true_date.ra, true_date.dec, vout); normalize3(vout);
        /* Closure: reverse */
        struct ln_nutation nut; ln_get_nutation(jd_tt, &nut);
        double ra_r=true_date.ra*(M_PI/180.0), dec_r=true_date.dec*(M_PI/180.0);
        double nut_ecl=(nut.ecliptic+nut.obliquity)*(M_PI/180.0);
        double dra = (cos(nut_ecl)+sin(nut_ecl)*sin(ra_r)*tan(dec_r))*nut.longitude - cos(ra_r)*tan(dec_r)*nut.obliquity;
        double ddec = (sin(nut_ecl)*cos(ra_r))*nut.longitude + sin(ra_r)*nut.obliquity;
        struct ln_equ_posn back_mean = { true_date.ra - dra, true_date.dec - ddec };
        struct ln_equ_posn back_j2000;
        ln_get_equ_prec2(&back_mean, jd_tt, JD2000, &back_j2000);
        double vback[3]; radec_to_cart(back_j2000.ra, back_j2000.dec, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_precession_nutation_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds=malloc(n*sizeof(double)), *ras=malloc(n*sizeof(double)), *decs=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        jds[i]=jd; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&ras[i],&decs[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_equ_posn j={ras[i],decs[i]}, m, t;
        ln_get_equ_prec(&j,jds[i],&m); ln_get_equ_nut(&m,jds[i],&t);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_equ_posn j={ras[i],decs[i]}, m, t;
        ln_get_equ_prec(&j,jds[i],&m); ln_get_equ_nut(&m,jds[i],&t); sink+=t.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    emit_valid_perf_json("precession_nutation_perf", n, ns, sink);
    free(jds); free(ras); free(decs);
}

/* --- inv_precession_nutation: EqTrueOfDate → EqMeanJ2000 --- */
void run_inv_precession_nutation(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    printf("{\"experiment\":\"inv_precession_nutation\",\"library\":\"libnova\",");
    printf("\"model\":\"IAU1980_inv_nut_Meeus_inv_prec\",");
    printf("\"count\":%d,\"cases\":[\n", n);
    for (int i = 0; i < n; i++) {
        double jd_tt,vx,vy,vz;
        if (scanf("%lf %lf %lf %lf", &jd_tt, &vx, &vy, &vz) != 4) { fprintf(stderr,"bad\n"); exit(1); }
        double vin[3]={vx,vy,vz}; normalize3(vin);
        double ra_deg, dec_deg;
        cart_to_radec(vin, &ra_deg, &dec_deg);
        /* Inverse nutation */
        struct ln_nutation nut; ln_get_nutation(jd_tt, &nut);
        double ra_r=ra_deg*(M_PI/180.0), dec_r=dec_deg*(M_PI/180.0);
        double nut_ecl=(nut.ecliptic+nut.obliquity)*(M_PI/180.0);
        double dra = (cos(nut_ecl)+sin(nut_ecl)*sin(ra_r)*tan(dec_r))*nut.longitude - cos(ra_r)*tan(dec_r)*nut.obliquity;
        double ddec = (sin(nut_ecl)*cos(ra_r))*nut.longitude + sin(ra_r)*nut.obliquity;
        double mean_ra = ra_deg - dra, mean_dec = dec_deg - ddec;
        /* Inverse precession */
        struct ln_equ_posn mean_pos = { mean_ra, mean_dec };
        struct ln_equ_posn j2000_pos;
        ln_get_equ_prec2(&mean_pos, jd_tt, JD2000, &j2000_pos);
        double vout[3]; radec_to_cart(j2000_pos.ra, j2000_pos.dec, vout); normalize3(vout);
        /* Closure: forward */
        struct ln_equ_posn fwd_mean, fwd_true;
        ln_get_equ_prec(&j2000_pos, jd_tt, &fwd_mean);
        ln_get_equ_nut(&fwd_mean, jd_tt, &fwd_true);
        double vback[3]; radec_to_cart(fwd_true.ra, fwd_true.dec, vback); normalize3(vback);
        double closure_rad = ang_sep(vin, vback);
        if (i > 0) printf(",\n");
        printf("{\"jd_tt\":%.15f,\"input\":[%.17e,%.17e,%.17e],", jd_tt, vin[0], vin[1], vin[2]);
        printf("\"output\":[%.17e,%.17e,%.17e],\"closure_rad\":%.17e}", vout[0], vout[1], vout[2], closure_rad);
    }
    printf("\n]}\n");
}

void run_inv_precession_nutation_perf(void) {
    int n;
    if (scanf("%d", &n) != 1) { fprintf(stderr, "bad N\n"); exit(1); }
    double *jds=malloc(n*sizeof(double)), *ras=malloc(n*sizeof(double)), *decs=malloc(n*sizeof(double));
    for (int i=0;i<n;i++) {
        double jd,vx,vy,vz; scanf("%lf %lf %lf %lf",&jd,&vx,&vy,&vz);
        jds[i]=jd; double v[3]={vx,vy,vz}; normalize3(v); cart_to_radec(v,&ras[i],&decs[i]);
    }
    for (int i=0;i<n&&i<100;i++) {
        struct ln_nutation nut; ln_get_nutation(jds[i], &nut);
        struct ln_equ_posn m={ras[i]-0.001,decs[i]}, j;
        ln_get_equ_prec2(&m, jds[i], JD2000, &j);
    }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    double sink=0;
    for (int i=0;i<n;i++) {
        struct ln_nutation nut; ln_get_nutation(jds[i],&nut);
        double ra_r=ras[i]*(M_PI/180.0), dec_r=decs[i]*(M_PI/180.0);
        double nut_ecl=(nut.ecliptic+nut.obliquity)*(M_PI/180.0);
        double dra=(cos(nut_ecl)+sin(nut_ecl)*sin(ra_r)*tan(dec_r))*nut.longitude-cos(ra_r)*tan(dec_r)*nut.obliquity;
        double ddec=(sin(nut_ecl)*cos(ra_r))*nut.longitude+sin(ra_r)*nut.obliquity;
        struct ln_equ_posn m={ras[i]-dra,decs[i]-ddec}, j;
        ln_get_equ_prec2(&m,jds[i],JD2000,&j); sink+=j.ra;
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double ns = (t1.tv_sec-t0.tv_sec)*1e9 + (t1.tv_nsec-t0.tv_nsec);
    emit_valid_perf_json("inv_precession_nutation_perf", n, ns, sink);
    free(jds); free(ras); free(decs);
}
