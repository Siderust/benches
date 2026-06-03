use std::io::{self, Write};
use std::time::Instant;

use crate::affn;
use crate::qtty::{Degrees, Meters, Radians};

use siderust::coordinates::cartesian;
use siderust::coordinates::centers::Geodetic;
use siderust::coordinates::frames::{EquatorialTrueOfDate, Horizontal, ECEF};
use siderust::coordinates::transform::horizontal::FromHorizontal;
use siderust::coordinates::transform::DirectionAstroExt;
use siderust::time::JulianDate;

use crate::ang_sep;

pub(crate) fn run_equ_horizontal(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    writeln!(
        out,
        "{{\"experiment\":\"equ_horizontal\",\"library\":\"siderust\",\
         \"model\":\"siderust_horizontal\",\
         \"count\":{},\"cases\":[",
        n
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let jd_ut1 = parts[0];
        let jd_tt_val = parts[1];
        let ra_rad = parts[2];
        let dec_rad = parts[3];
        let obs_lon_rad = parts[4];
        let obs_lat_rad = parts[5];

        let jd_ut1_q = JulianDate::new(jd_ut1);
        let jd_tt_q = JulianDate::new(jd_tt_val);

        // Create equatorial true-of-date cartesian direction
        let spherical_equ = affn::spherical::Direction::<EquatorialTrueOfDate>::new_raw(
            Degrees::new(dec_rad.to_degrees()),
            Degrees::new(ra_rad.to_degrees()),
        );
        let equatorial_direction = spherical_equ.to_cartesian();

        // Create observer site
        let site = Geodetic::<ECEF>::new(
            Degrees::new(obs_lon_rad.to_degrees()),
            Degrees::new(obs_lat_rad.to_degrees()),
            Meters::new(0.0),
        );

        // Transform to horizontal (precise: explicit UT1+TT for benchmark fairness)
        let horizontal_direction = DirectionAstroExt::to_horizontal_precise(
            &equatorial_direction,
            &jd_tt_q,
            &jd_ut1_q,
            &site,
        );
        let horizontal_spherical = horizontal_direction.to_spherical();
        let az = Radians::from(horizontal_spherical.azimuth);
        let alt = Radians::from(horizontal_spherical.polar);

        // Transform back to equatorial
        let equatorial_back: affn::cartesian::Direction<EquatorialTrueOfDate> =
            horizontal_direction.to_equatorial(&jd_ut1_q, &jd_tt_q, &site);
        let equatorial_back_spherical = equatorial_back.to_spherical();
        let ra_back = Radians::from(equatorial_back_spherical.azimuth);
        let dec_back = Radians::from(equatorial_back_spherical.polar);

        let v_in = [
            dec_rad.cos() * ra_rad.cos(),
            dec_rad.cos() * ra_rad.sin(),
            dec_rad.sin(),
        ];
        let v_back = [
            dec_back.value().cos() * ra_back.value().cos(),
            dec_back.value().cos() * ra_back.value().sin(),
            dec_back.value().sin(),
        ];
        let closure_rad = ang_sep(&v_in, &v_back);

        if i > 0 {
            writeln!(out, ",").unwrap();
        }
        write!(
            out,
            "{{\"jd_ut1\":{:.15},\"jd_tt\":{:.15},\
             \"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\
             \"obs_lon_rad\":{:.17e},\"obs_lat_rad\":{:.17e},\
             \"az_rad\":{:.17e},\"alt_rad\":{:.17e},\
             \"closure_rad\":{:.17e}}}",
            jd_ut1,
            jd_tt_val,
            ra_rad,
            dec_rad,
            obs_lon_rad,
            obs_lat_rad,
            az.value(),
            alt.value(),
            closure_rad,
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_equ_horizontal_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut params: Vec<(f64, f64, f64, f64, f64, f64)> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        params.push((parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]));
    }

    // Warm-up
    let warmup = crate::perf_warmup();
    for &(jd_ut1, jd_tt, ra, dec, lon, lat) in params.iter().take(n.min(warmup)) {
        let jd_ut1_q = JulianDate::new(jd_ut1);
        let jd_tt_q = JulianDate::new(jd_tt);

        let spherical_equ = affn::spherical::Direction::<EquatorialTrueOfDate>::new_raw(
            Degrees::new(dec.to_degrees()),
            Degrees::new(ra.to_degrees()),
        );
        let equatorial_direction = spherical_equ.to_cartesian();
        let site = Geodetic::<ECEF>::new(
            Degrees::new(lon.to_degrees()),
            Degrees::new(lat.to_degrees()),
            Meters::new(0.0),
        );
        let dir_hor = equatorial_direction.to_horizontal_precise(&jd_tt_q, &jd_ut1_q, &site);
        std::hint::black_box(&dir_hor);
    }

    // Timed run
    let start = Instant::now();
    let mut sink: (f64, f64) = (0.0, 0.0);
    for &(jd_ut1, jd_tt, ra, dec, lon, lat) in &params {
        let jd_ut1_q = JulianDate::new(jd_ut1);
        let jd_tt_q = JulianDate::new(jd_tt);

        let spherical_equ = affn::spherical::Direction::<EquatorialTrueOfDate>::new_raw(
            Degrees::new(dec.to_degrees()),
            Degrees::new(ra.to_degrees()),
        );
        let equatorial_direction = spherical_equ.to_cartesian();
        let site = Geodetic::<ECEF>::new(
            Degrees::new(lon.to_degrees()),
            Degrees::new(lat.to_degrees()),
            Meters::new(0.0),
        );
        let horizontal_direction =
            equatorial_direction.to_horizontal_precise(&jd_tt_q, &jd_ut1_q, &site);
        let horizontal_spherical = horizontal_direction.to_spherical();
        let az = Radians::from(horizontal_spherical.azimuth);
        let alt = Radians::from(horizontal_spherical.polar);
        sink = (az.value(), alt.value());
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    let per_op_ns = total_ns / n as f64;

    println!(
        "{{\"experiment\":\"equ_horizontal_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        per_op_ns,
        n as f64 / (total_ns * 1e-9),
        sink.0,
    );
}

pub fn run_horiz_to_equ(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    writeln!(
        out,
        "{{\"experiment\":\"horiz_to_equ\",\"library\":\"siderust\",\
         \"model\":\"siderust_horizontal_inverse\",\
         \"count\":{},\"cases\":[",
        n
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let jd_ut1_val = parts[0];
        let jd_tt_val = parts[1];
        let az_rad = parts[2];
        let alt_rad = parts[3];
        let obs_lon_rad = parts[4];
        let obs_lat_rad = parts[5];

        let jd_ut1 = JulianDate::new(jd_ut1_val);
        let jd_tt = JulianDate::new(jd_tt_val);
        let site = Geodetic::<ECEF>::new(
            Degrees::new(obs_lon_rad.to_degrees()),
            Degrees::new(obs_lat_rad.to_degrees()),
            Meters::new(0.0),
        );

        let sph_hor = affn::spherical::Direction::<Horizontal>::new_raw(
            Degrees::new(alt_rad.to_degrees()),
            Degrees::new(az_rad.to_degrees()),
        );
        let hor_dir = sph_hor.to_cartesian();

        let equ_dir: cartesian::Direction<EquatorialTrueOfDate> =
            hor_dir.to_equatorial(&jd_ut1, &jd_tt, &site);
        let equ_sph = equ_dir.to_spherical();
        let ra = Radians::from(equ_sph.azimuth);
        let dec = Radians::from(equ_sph.polar);

        let hor_back = DirectionAstroExt::to_horizontal_precise(&equ_dir, &jd_tt, &jd_ut1, &site);
        let equ_back: cartesian::Direction<EquatorialTrueOfDate> =
            hor_back.to_equatorial(&jd_ut1, &jd_tt, &site);
        let equ_back_sph = equ_back.to_spherical();
        let ra_back = Radians::from(equ_back_sph.azimuth);
        let dec_back = Radians::from(equ_back_sph.polar);

        let v_in = [
            dec.value().cos() * ra.value().cos(),
            dec.value().cos() * ra.value().sin(),
            dec.value().sin(),
        ];
        let v_back = [
            dec_back.value().cos() * ra_back.value().cos(),
            dec_back.value().cos() * ra_back.value().sin(),
            dec_back.value().sin(),
        ];
        let closure_rad = ang_sep(&v_in, &v_back);

        if i > 0 {
            writeln!(out, ",").unwrap();
        }
        write!(
            out,
            "{{\"jd_ut1\":{:.15},\"jd_tt\":{:.15},\
             \"az_rad\":{:.17e},\"alt_rad\":{:.17e},\
             \"obs_lon_rad\":{:.17e},\"obs_lat_rad\":{:.17e},\
             \"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\
             \"closure_rad\":{:.17e}}}",
            jd_ut1_val,
            jd_tt_val,
            az_rad,
            alt_rad,
            obs_lon_rad,
            obs_lat_rad,
            ra.value(),
            dec.value(),
            closure_rad,
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub fn run_horiz_to_equ_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut params: Vec<(f64, f64, f64, f64, f64, f64)> = Vec::with_capacity(n);
    for _ in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        params.push((parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]));
    }

    let warmup = crate::perf_warmup();
    for &(jd_ut1_v, jd_tt_v, az, alt, lon, lat) in params.iter().take(n.min(warmup)) {
        let jd_ut1 = JulianDate::new(jd_ut1_v);
        let jd_tt = JulianDate::new(jd_tt_v);
        let site = Geodetic::<ECEF>::new(
            Degrees::new(lon.to_degrees()),
            Degrees::new(lat.to_degrees()),
            Meters::new(0.0),
        );
        let sph = affn::spherical::Direction::<Horizontal>::new_raw(
            Degrees::new(alt.to_degrees()),
            Degrees::new(az.to_degrees()),
        );
        let hor = sph.to_cartesian();
        let d: cartesian::Direction<EquatorialTrueOfDate> =
            hor.to_equatorial(&jd_ut1, &jd_tt, &site);
        std::hint::black_box(&d);
    }

    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for &(jd_ut1_v, jd_tt_v, az, alt, lon, lat) in &params {
        let jd_ut1 = JulianDate::new(jd_ut1_v);
        let jd_tt = JulianDate::new(jd_tt_v);
        let site = Geodetic::<ECEF>::new(
            Degrees::new(lon.to_degrees()),
            Degrees::new(lat.to_degrees()),
            Meters::new(0.0),
        );
        let sph = affn::spherical::Direction::<Horizontal>::new_raw(
            Degrees::new(alt.to_degrees()),
            Degrees::new(az.to_degrees()),
        );
        let hor = sph.to_cartesian();
        let equ: cartesian::Direction<EquatorialTrueOfDate> =
            hor.to_equatorial(&jd_ut1, &jd_tt, &site);
        let equ_sph = equ.to_spherical();
        let ra = Radians::from(equ_sph.azimuth);
        let dec = Radians::from(equ_sph.polar);
        sink += ra.value() + dec.value();
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;

    println!(
        "{{\"experiment\":\"horiz_to_equ_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        total_ns / n as f64,
        n as f64 / (total_ns * 1e-9),
        sink,
    );
}
