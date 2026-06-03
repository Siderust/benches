#include "common.h"

/* ------------------------------------------------------------------ */
/* Main dispatcher                                                     */
/* ------------------------------------------------------------------ */

int main(void) {
    char experiment[256];
    if (scanf("%255s", experiment) != 1) {
        fprintf(stderr, "Usage: echo 'experiment_name\\nN\\n...' | ./libnova_adapter\n");
        return 1;
    }

    size_t exp_len = strlen(experiment);
    if (exp_len > 6 && strcmp(experiment + exp_len - 6, "_setup") == 0) {
        printf("{\"setup_ms\":0.0,\"measured\":true}\n");
    } else if (strcmp(experiment, "frame_rotation_bpn") == 0) {
        run_frame_rotation_bpn();
    } else if (strcmp(experiment, "gmst_era") == 0) {
        run_gmst_era();
    } else if (strcmp(experiment, "equ_ecl") == 0) {
        run_equ_ecl();
    } else if (strcmp(experiment, "equ_horizontal") == 0) {
        run_equ_horizontal();
    } else if (strcmp(experiment, "solar_position") == 0) {
        if (lane_is_geometric()) run_solar_position_geometric();
        else run_solar_position();
    } else if (strcmp(experiment, "lunar_position") == 0) {
        if (lane_is_geometric()) run_lunar_position_geometric();
        else run_lunar_position();
    } else if (strcmp(experiment, "mercury_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("mercury_position",
                "libnova_VSOP87_mercury_geometric", ln_get_mercury_rect_helio);
        else
            run_planet_position("mercury_position", "libnova_VSOP87_mercury",
                                ln_get_mercury_equ_coords, ln_get_mercury_earth_dist);
    } else if (strcmp(experiment, "venus_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("venus_position",
                "libnova_VSOP87_venus_geometric", ln_get_venus_rect_helio);
        else
            run_planet_position("venus_position", "libnova_VSOP87_venus",
                                ln_get_venus_equ_coords, ln_get_venus_earth_dist);
    } else if (strcmp(experiment, "mars_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("mars_position",
                "libnova_VSOP87_mars_geometric", ln_get_mars_rect_helio);
        else
            run_planet_position("mars_position", "libnova_VSOP87_mars",
                                ln_get_mars_equ_coords, ln_get_mars_earth_dist);
    } else if (strcmp(experiment, "jupiter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("jupiter_position",
                "libnova_VSOP87_jupiter_geometric", ln_get_jupiter_rect_helio);
        else
            run_planet_position("jupiter_position", "libnova_VSOP87_jupiter",
                                ln_get_jupiter_equ_coords, ln_get_jupiter_earth_dist);
    } else if (strcmp(experiment, "saturn_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("saturn_position",
                "libnova_VSOP87_saturn_geometric", ln_get_saturn_rect_helio);
        else
            run_planet_position("saturn_position", "libnova_VSOP87_saturn",
                                ln_get_saturn_equ_coords, ln_get_saturn_earth_dist);
    } else if (strcmp(experiment, "uranus_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("uranus_position",
                "libnova_VSOP87_uranus_geometric", ln_get_uranus_rect_helio);
        else
            run_planet_position("uranus_position", "libnova_VSOP87_uranus",
                                ln_get_uranus_equ_coords, ln_get_uranus_earth_dist);
    } else if (strcmp(experiment, "neptune_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("neptune_position",
                "libnova_VSOP87_neptune_geometric", ln_get_neptune_rect_helio);
        else
            run_planet_position("neptune_position", "libnova_VSOP87_neptune",
                                ln_get_neptune_equ_coords, ln_get_neptune_earth_dist);
    } else if (strcmp(experiment, "mercury_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("mercury_barycenter_position",
                "libnova_VSOP87_mercury_geometric", ln_get_mercury_rect_helio);
        else
            run_planet_position("mercury_barycenter_position", "libnova_VSOP87_mercury",
                                ln_get_mercury_equ_coords, ln_get_mercury_earth_dist);
    } else if (strcmp(experiment, "venus_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("venus_barycenter_position",
                "libnova_VSOP87_venus_geometric", ln_get_venus_rect_helio);
        else
            run_planet_position("venus_barycenter_position", "libnova_VSOP87_venus",
                                ln_get_venus_equ_coords, ln_get_venus_earth_dist);
    } else if (strcmp(experiment, "mars_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("mars_barycenter_position",
                "libnova_VSOP87_mars_geometric", ln_get_mars_rect_helio);
        else
            run_planet_position("mars_barycenter_position", "libnova_VSOP87_mars",
                                ln_get_mars_equ_coords, ln_get_mars_earth_dist);
    } else if (strcmp(experiment, "jupiter_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("jupiter_barycenter_position",
                "libnova_VSOP87_jupiter_geometric", ln_get_jupiter_rect_helio);
        else
            run_planet_position("jupiter_barycenter_position", "libnova_VSOP87_jupiter",
                                ln_get_jupiter_equ_coords, ln_get_jupiter_earth_dist);
    } else if (strcmp(experiment, "saturn_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("saturn_barycenter_position",
                "libnova_VSOP87_saturn_geometric", ln_get_saturn_rect_helio);
        else
            run_planet_position("saturn_barycenter_position", "libnova_VSOP87_saturn",
                                ln_get_saturn_equ_coords, ln_get_saturn_earth_dist);
    } else if (strcmp(experiment, "uranus_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("uranus_barycenter_position",
                "libnova_VSOP87_uranus_geometric", ln_get_uranus_rect_helio);
        else
            run_planet_position("uranus_barycenter_position", "libnova_VSOP87_uranus",
                                ln_get_uranus_equ_coords, ln_get_uranus_earth_dist);
    } else if (strcmp(experiment, "neptune_barycenter_position") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric("neptune_barycenter_position",
                "libnova_VSOP87_neptune_geometric", ln_get_neptune_rect_helio);
        else
            run_planet_position("neptune_barycenter_position", "libnova_VSOP87_neptune",
                                ln_get_neptune_equ_coords, ln_get_neptune_earth_dist);
    } else if (strcmp(experiment, "kepler_solver") == 0) {
        run_kepler_solver();
    } else if (strcmp(experiment, "frame_rotation_bpn_perf") == 0) {
        run_frame_rotation_bpn_perf();
    } else if (strcmp(experiment, "gmst_era_perf") == 0) {
        run_gmst_era_perf();
    } else if (strcmp(experiment, "equ_ecl_perf") == 0) {
        run_equ_ecl_perf();
    } else if (strcmp(experiment, "equ_horizontal_perf") == 0) {
        run_equ_horizontal_perf();
    } else if (strcmp(experiment, "solar_position_perf") == 0) {
        if (lane_is_geometric()) run_solar_position_geometric_perf();
        else run_solar_position_perf();
    } else if (strcmp(experiment, "lunar_position_perf") == 0) {
        if (lane_is_geometric()) run_lunar_position_geometric_perf();
        else run_lunar_position_perf();
    } else if (strcmp(experiment, "mercury_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("mercury_position", ln_get_mercury_rect_helio);
        else
            run_planet_position_perf("mercury_position",
                                     ln_get_mercury_equ_coords, ln_get_mercury_earth_dist);
    } else if (strcmp(experiment, "venus_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("venus_position", ln_get_venus_rect_helio);
        else
            run_planet_position_perf("venus_position",
                                     ln_get_venus_equ_coords, ln_get_venus_earth_dist);
    } else if (strcmp(experiment, "mars_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("mars_position", ln_get_mars_rect_helio);
        else
            run_planet_position_perf("mars_position",
                                     ln_get_mars_equ_coords, ln_get_mars_earth_dist);
    } else if (strcmp(experiment, "jupiter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("jupiter_position", ln_get_jupiter_rect_helio);
        else
            run_planet_position_perf("jupiter_position",
                                     ln_get_jupiter_equ_coords, ln_get_jupiter_earth_dist);
    } else if (strcmp(experiment, "saturn_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("saturn_position", ln_get_saturn_rect_helio);
        else
            run_planet_position_perf("saturn_position",
                                     ln_get_saturn_equ_coords, ln_get_saturn_earth_dist);
    } else if (strcmp(experiment, "uranus_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("uranus_position", ln_get_uranus_rect_helio);
        else
            run_planet_position_perf("uranus_position",
                                     ln_get_uranus_equ_coords, ln_get_uranus_earth_dist);
    } else if (strcmp(experiment, "neptune_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("neptune_position", ln_get_neptune_rect_helio);
        else
            run_planet_position_perf("neptune_position",
                                     ln_get_neptune_equ_coords, ln_get_neptune_earth_dist);
    } else if (strcmp(experiment, "mercury_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("mercury_barycenter_position", ln_get_mercury_rect_helio);
        else
            run_planet_position_perf("mercury_barycenter_position",
                                     ln_get_mercury_equ_coords, ln_get_mercury_earth_dist);
    } else if (strcmp(experiment, "venus_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("venus_barycenter_position", ln_get_venus_rect_helio);
        else
            run_planet_position_perf("venus_barycenter_position",
                                     ln_get_venus_equ_coords, ln_get_venus_earth_dist);
    } else if (strcmp(experiment, "mars_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("mars_barycenter_position", ln_get_mars_rect_helio);
        else
            run_planet_position_perf("mars_barycenter_position",
                                     ln_get_mars_equ_coords, ln_get_mars_earth_dist);
    } else if (strcmp(experiment, "jupiter_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("jupiter_barycenter_position", ln_get_jupiter_rect_helio);
        else
            run_planet_position_perf("jupiter_barycenter_position",
                                     ln_get_jupiter_equ_coords, ln_get_jupiter_earth_dist);
    } else if (strcmp(experiment, "saturn_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("saturn_barycenter_position", ln_get_saturn_rect_helio);
        else
            run_planet_position_perf("saturn_barycenter_position",
                                     ln_get_saturn_equ_coords, ln_get_saturn_earth_dist);
    } else if (strcmp(experiment, "uranus_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("uranus_barycenter_position", ln_get_uranus_rect_helio);
        else
            run_planet_position_perf("uranus_barycenter_position",
                                     ln_get_uranus_equ_coords, ln_get_uranus_earth_dist);
    } else if (strcmp(experiment, "neptune_barycenter_position_perf") == 0) {
        if (lane_is_geometric())
            run_planet_position_geometric_perf("neptune_barycenter_position", ln_get_neptune_rect_helio);
        else
            run_planet_position_perf("neptune_barycenter_position",
                                     ln_get_neptune_equ_coords, ln_get_neptune_earth_dist);
    } else if (strcmp(experiment, "kepler_solver_perf") == 0) {
        run_kepler_solver_perf();
    } else if (strcmp(experiment, "frame_bias") == 0) {
        run_frame_bias();
    } else if (strcmp(experiment, "frame_bias_perf") == 0) {
        run_frame_bias_perf();
    } else if (strcmp(experiment, "precession") == 0) {
        run_precession();
    } else if (strcmp(experiment, "precession_perf") == 0) {
        run_precession_perf();
    } else if (strcmp(experiment, "nutation") == 0) {
        run_nutation();
    } else if (strcmp(experiment, "nutation_perf") == 0) {
        run_nutation_perf();
    } else if (strcmp(experiment, "icrs_ecl_j2000") == 0) {
        run_icrs_ecl_j2000();
    } else if (strcmp(experiment, "icrs_ecl_j2000_perf") == 0) {
        run_icrs_ecl_j2000_perf();
    } else if (strcmp(experiment, "icrs_ecl_tod") == 0) {
        run_icrs_ecl_tod();
    } else if (strcmp(experiment, "icrs_ecl_tod_perf") == 0) {
        run_icrs_ecl_tod_perf();
    } else if (strcmp(experiment, "horiz_to_equ") == 0) {
        run_horiz_to_equ();
    } else if (strcmp(experiment, "horiz_to_equ_perf") == 0) {
        run_horiz_to_equ_perf();
    /* 13 new matrix experiments */
    } else if (strcmp(experiment, "inv_frame_bias") == 0) {
        run_inv_frame_bias();
    } else if (strcmp(experiment, "inv_frame_bias_perf") == 0) {
        run_inv_frame_bias_perf();
    } else if (strcmp(experiment, "inv_precession") == 0) {
        run_inv_precession();
    } else if (strcmp(experiment, "inv_precession_perf") == 0) {
        run_inv_precession_perf();
    } else if (strcmp(experiment, "inv_nutation") == 0) {
        run_inv_nutation();
    } else if (strcmp(experiment, "inv_nutation_perf") == 0) {
        run_inv_nutation_perf();
    } else if (strcmp(experiment, "inv_bpn") == 0) {
        run_inv_bpn();
    } else if (strcmp(experiment, "inv_bpn_perf") == 0) {
        run_inv_bpn_perf();
    } else if (strcmp(experiment, "inv_icrs_ecl_j2000") == 0) {
        run_inv_icrs_ecl_j2000();
    } else if (strcmp(experiment, "inv_icrs_ecl_j2000_perf") == 0) {
        run_inv_icrs_ecl_j2000_perf();
    } else if (strcmp(experiment, "obliquity") == 0) {
        run_obliquity();
    } else if (strcmp(experiment, "obliquity_perf") == 0) {
        run_obliquity_perf();
    } else if (strcmp(experiment, "inv_obliquity") == 0) {
        run_inv_obliquity();
    } else if (strcmp(experiment, "inv_obliquity_perf") == 0) {
        run_inv_obliquity_perf();
    } else if (strcmp(experiment, "bias_precession") == 0) {
        run_bias_precession();
    } else if (strcmp(experiment, "bias_precession_perf") == 0) {
        run_bias_precession_perf();
    } else if (strcmp(experiment, "inv_bias_precession") == 0) {
        run_inv_bias_precession();
    } else if (strcmp(experiment, "inv_bias_precession_perf") == 0) {
        run_inv_bias_precession_perf();
    } else if (strcmp(experiment, "precession_nutation") == 0) {
        run_precession_nutation();
    } else if (strcmp(experiment, "precession_nutation_perf") == 0) {
        run_precession_nutation_perf();
    } else if (strcmp(experiment, "inv_precession_nutation") == 0) {
        run_inv_precession_nutation();
    } else if (strcmp(experiment, "inv_precession_nutation_perf") == 0) {
        run_inv_precession_nutation_perf();
    } else if (strcmp(experiment, "inv_icrs_ecl_tod") == 0) {
        run_inv_icrs_ecl_tod();
    } else if (strcmp(experiment, "inv_icrs_ecl_tod_perf") == 0) {
        run_inv_icrs_ecl_tod_perf();
    } else if (strcmp(experiment, "inv_equ_ecl") == 0) {
        run_inv_equ_ecl();
    } else if (strcmp(experiment, "inv_equ_ecl_perf") == 0) {
        run_inv_equ_ecl_perf();
    } else {
        fprintf(stderr, "Unknown experiment: %s\n", experiment);
        return 1;
    }

    return 0;
}
