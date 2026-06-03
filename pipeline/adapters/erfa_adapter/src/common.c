#include "common.h"

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

void normalize3(double v[3]) {
    double r = sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
    if (r > 0.0) { v[0] /= r; v[1] /= r; v[2] /= r; }
}

int get_perf_warmup(void) {
    char *w = getenv("LAB_PERF_WARMUP");
    if (!w) return 100;
    int v = atoi(w);
    if (v < 0) return 0;
    return v;
}

/* Multiply 3x3 matrix by 3-vector: out = m * v */
void mv3(double m[3][3], const double v[3], double out[3]) {
    for (int i = 0; i < 3; i++) {
        out[i] = m[i][0]*v[0] + m[i][1]*v[1] + m[i][2]*v[2];
    }
}

/* Angular separation between two unit vectors (radians) */
double ang_sep(const double a[3], const double b[3]) {
    double dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
    if (dot >  1.0) dot =  1.0;
    if (dot < -1.0) dot = -1.0;
    return acos(dot);
}

/* Normalize angle to [0, 2π) */
double normalize_angle(double a) {
    a = fmod(a, 2.0 * M_PI);
    if (a < 0.0) a += 2.0 * M_PI;
    return a;
}
