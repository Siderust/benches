#include "common.h"

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

void normalize3(double v[3]) {
    double r = sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
    if (r > 0.0) { v[0] /= r; v[1] /= r; v[2] /= r; }
}

/* Convert Cartesian unit vector to RA/Dec in degrees */
void cart_to_radec(const double v[3], double *ra_deg, double *dec_deg) {
    *dec_deg = asin(v[2]) * (180.0 / M_PI);
    *ra_deg  = atan2(v[1], v[0]) * (180.0 / M_PI);
    if (*ra_deg < 0.0) *ra_deg += 360.0;
}

/* Convert RA/Dec in degrees to Cartesian unit vector */
void radec_to_cart(double ra_deg, double dec_deg, double v[3]) {
    double ra_r  = ra_deg  * (M_PI / 180.0);
    double dec_r = dec_deg * (M_PI / 180.0);
    v[0] = cos(dec_r) * cos(ra_r);
    v[1] = cos(dec_r) * sin(ra_r);
    v[2] = sin(dec_r);
}

/* Angular separation between two unit vectors (radians) */
double ang_sep(const double a[3], const double b[3]) {
    double dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
    if (dot >  1.0) dot =  1.0;
    if (dot < -1.0) dot = -1.0;
    return acos(dot);
}

/* ------------------------------------------------------------------ */
/* Apply nutation to equatorial coordinates (Meeus Equ. 22.1)         */
/* in:  pos->ra/dec in degrees, jd in TT                              */
/* out: out->ra/dec in degrees (nutation corrections added)           */
/* ------------------------------------------------------------------ */

void ln_get_equ_nut(const struct ln_equ_posn *pos, double jd,
                           struct ln_equ_posn *out)
{
    struct ln_nutation nut;
    ln_get_nutation(jd, &nut);

    double ra_r  = pos->ra  * (M_PI / 180.0);
    double dec_r = pos->dec * (M_PI / 180.0);

    double epsilon      = (nut.ecliptic + nut.obliquity) * (M_PI / 180.0);
    double sin_epsilon  = sin(epsilon);
    double cos_epsilon  = cos(epsilon);
    double sin_ra       = sin(ra_r);
    double cos_ra       = cos(ra_r);
    double tan_dec      = tan(dec_r);

    double delta_ra  = (cos_epsilon + sin_epsilon * sin_ra * tan_dec) * nut.longitude
                     - cos_ra * tan_dec * nut.obliquity;
    double delta_dec = (sin_epsilon * cos_ra) * nut.longitude
                     + sin_ra * nut.obliquity;

    out->ra  = pos->ra  + delta_ra;
    out->dec = pos->dec + delta_dec;
}

/* ------------------------------------------------------------------ */
/* Forward transform: J2000 → epoch (precession then nutation)         */
/* ------------------------------------------------------------------ */

void j2000_to_epoch(double jd_tt, const double vin[3], double vout[3]) {
    double ra_deg, dec_deg;
    cart_to_radec(vin, &ra_deg, &dec_deg);

    /* 1. Precession: J2000 → epoch */
    struct ln_equ_posn mean_pos = { .ra = ra_deg, .dec = dec_deg };
    struct ln_equ_posn prec_pos;
    ln_get_equ_prec(&mean_pos, jd_tt, &prec_pos);

    /* 2. Nutation: apply nutation correction */
    struct ln_equ_posn nut_pos;
    ln_get_equ_nut(&prec_pos, jd_tt, &nut_pos);

    radec_to_cart(nut_pos.ra, nut_pos.dec, vout);
    normalize3(vout);
}

/* ------------------------------------------------------------------ */
/* Reverse transform: epoch → J2000 (undo nutation then precession)    */
/* ------------------------------------------------------------------ */

void epoch_to_j2000(double jd_tt, const double vin[3], double vout[3]) {
    double ra_deg, dec_deg;
    cart_to_radec(vin, &ra_deg, &dec_deg);

    /*
     * Undo nutation: ln_get_equ_nut applies additive RA/Dec corrections
     * using the nutation parameters. To reverse, we compute the same
     * corrections and subtract them.
     */
    struct ln_nutation nut;
    ln_get_nutation(jd_tt, &nut);

    double ra_r  = ra_deg * (M_PI / 180.0);
    double dec_r = dec_deg * (M_PI / 180.0);

    double nut_ecliptic = (nut.ecliptic + nut.obliquity) * (M_PI / 180.0);
    double sin_ecliptic = sin(nut_ecliptic);
    double sin_ra = sin(ra_r);
    double cos_ra = cos(ra_r);
    double tan_dec = tan(dec_r);

    /* Same formula as ln_get_equ_nut (Meeus Equ 22.1), but subtracted */
    double delta_ra = (cos(nut_ecliptic) + sin_ecliptic * sin_ra * tan_dec) * nut.longitude
                    - cos_ra * tan_dec * nut.obliquity;
    double delta_dec = (sin_ecliptic * cos_ra) * nut.longitude
                     + sin_ra * nut.obliquity;

    double unnut_ra  = ra_deg  - delta_ra;
    double unnut_dec = dec_deg - delta_dec;

    /* Undo precession: epoch → J2000 */
    struct ln_equ_posn epoch_pos = { .ra = unnut_ra, .dec = unnut_dec };
    struct ln_equ_posn j2000_pos;
    ln_get_equ_prec2(&epoch_pos, jd_tt, JD2000, &j2000_pos);

    radec_to_cart(j2000_pos.ra, j2000_pos.dec, vout);
    normalize3(vout);
}
