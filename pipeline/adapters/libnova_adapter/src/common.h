#ifndef LIBNOVA_ADAPTER_COMMON_H
#define LIBNOVA_ADAPTER_COMMON_H

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#include <libnova/precession.h>
#include <libnova/nutation.h>
#include <libnova/sidereal_time.h>
#include <libnova/ln_types.h>
#include <libnova/utility.h>
#include <libnova/transform.h>
#include <libnova/solar.h>
#include <libnova/lunar.h>
#include <libnova/mercury.h>
#include <libnova/venus.h>
#include <libnova/mars.h>
#include <libnova/jupiter.h>
#include <libnova/saturn.h>
#include <libnova/uranus.h>
#include <libnova/neptune.h>
#include <libnova/earth.h>
#include <libnova/elliptic_motion.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef void (*planet_equ_fn_t)(double, struct ln_equ_posn *);
typedef double (*planet_dist_fn_t)(double);
typedef void (*planet_rect_helio_fn_t)(double, struct ln_rect_posn *);

void normalize3(double v[3]);
void cart_to_radec(const double v[3], double *ra_deg, double *dec_deg);
void radec_to_cart(double ra_deg, double dec_deg, double v[3]);
double ang_sep(const double a[3], const double b[3]);
void ln_get_equ_nut(const struct ln_equ_posn *pos, double jd, struct ln_equ_posn *out);
void j2000_to_epoch(double jd_tt, const double vin[3], double vout[3]);
void epoch_to_j2000(double jd_tt, const double vin[3], double vout[3]);
int lane_is_geometric(void);

void run_frame_rotation_bpn(void);
void run_gmst_era(void);
void run_equ_ecl(void);
void run_equ_horizontal(void);
void run_solar_position(void);
void run_lunar_position(void);
void run_solar_position_geometric(void);
void run_lunar_position_geometric(void);
void run_solar_position_geometric_perf(void);
void run_lunar_position_geometric_perf(void);
void run_kepler_solver(void);
void run_frame_rotation_bpn_perf(void);
void run_gmst_era_perf(void);
void run_equ_ecl_perf(void);
void run_equ_horizontal_perf(void);
void run_solar_position_perf(void);
void run_lunar_position_perf(void);
void run_kepler_solver_perf(void);
void run_frame_bias(void);
void run_frame_bias_perf(void);
void run_precession(void);
void run_precession_perf(void);
void run_nutation(void);
void run_nutation_perf(void);
void run_icrs_ecl_j2000(void);
void run_icrs_ecl_j2000_perf(void);
void run_icrs_ecl_tod(void);
void run_icrs_ecl_tod_perf(void);
void run_horiz_to_equ(void);
void run_horiz_to_equ_perf(void);
void run_inv_frame_bias(void);
void run_inv_frame_bias_perf(void);
void run_inv_bpn(void);
void run_inv_bpn_perf(void);
void run_bias_precession(void);
void run_bias_precession_perf(void);
void run_inv_bias_precession(void);
void run_inv_bias_precession_perf(void);
void run_inv_precession(void);
void run_inv_precession_perf(void);
void run_inv_nutation(void);
void run_inv_nutation_perf(void);
void run_inv_icrs_ecl_j2000(void);
void run_inv_icrs_ecl_j2000_perf(void);
void run_obliquity(void);
void run_obliquity_perf(void);
void run_inv_obliquity(void);
void run_inv_obliquity_perf(void);
void run_precession_nutation(void);
void run_precession_nutation_perf(void);
void run_inv_precession_nutation(void);
void run_inv_precession_nutation_perf(void);
void run_inv_icrs_ecl_tod(void);
void run_inv_icrs_ecl_tod_perf(void);
void run_inv_equ_ecl(void);
void run_inv_equ_ecl_perf(void);
void run_planet_position(const char *experiment, const char *model, planet_equ_fn_t equ_fn, planet_dist_fn_t dist_fn);
void run_planet_position_geometric(const char *experiment, const char *model, planet_rect_helio_fn_t rect_helio_fn);
void run_planet_position_perf(const char *experiment, planet_equ_fn_t equ_fn, planet_dist_fn_t dist_fn);
void run_planet_position_geometric_perf(const char *experiment, planet_rect_helio_fn_t rect_helio_fn);

int get_perf_warmup(void);
void emit_valid_perf_json(const char *experiment, int count, double elapsed_ns, double sink);

#endif
