#ifndef ERFA_ADAPTER_COMMON_H
#define ERFA_ADAPTER_COMMON_H

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include "erfa.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void normalize3(double v[3]);
void mv3(double m[3][3], const double v[3], double out[3]);
double ang_sep(const double a[3], const double b[3]);
double normalize_angle(double a);

void run_frame_rotation_bpn(void);
void run_frame_rotation_bpn_perf(void);
void run_gmst_era(void);
void run_gmst_era_perf(void);
void run_frame_bias(void);
void run_frame_bias_perf(void);
void run_precession(void);
void run_precession_perf(void);
void run_nutation(void);
void run_nutation_perf(void);
void run_inv_frame_bias(void);
void run_inv_frame_bias_perf(void);
void run_inv_precession(void);
void run_inv_precession_perf(void);
void run_inv_nutation(void);
void run_inv_nutation_perf(void);
void run_inv_bpn(void);
void run_inv_bpn_perf(void);
void run_obliquity(void);
void run_obliquity_perf(void);
void run_inv_obliquity(void);
void run_inv_obliquity_perf(void);
void run_bias_precession(void);
void run_bias_precession_perf(void);
void run_inv_bias_precession(void);
void run_inv_bias_precession_perf(void);
void run_precession_nutation(void);
void run_precession_nutation_perf(void);
void run_inv_precession_nutation(void);
void run_inv_precession_nutation_perf(void);

void run_equ_ecl(void);
void run_equ_ecl_perf(void);
void run_icrs_ecl_j2000(void);
void run_icrs_ecl_j2000_perf(void);
void run_icrs_ecl_tod(void);
void run_icrs_ecl_tod_perf(void);
void run_inv_icrs_ecl_j2000(void);
void run_inv_icrs_ecl_j2000_perf(void);
void run_inv_icrs_ecl_tod(void);
void run_inv_icrs_ecl_tod_perf(void);
void run_inv_equ_ecl(void);
void run_inv_equ_ecl_perf(void);

void run_equ_horizontal(void);
void run_equ_horizontal_perf(void);
void run_horiz_to_equ(void);
void run_horiz_to_equ_perf(void);

void run_solar_position(void);
void run_solar_position_perf(void);
void run_lunar_position(void);
void run_lunar_position_perf(void);
void run_planet_position(const char *experiment, const char *planet_name, int np);
void run_planet_position_perf(const char *experiment, int np);

void run_kepler_solver(void);
void run_kepler_solver_perf(void);

#endif
