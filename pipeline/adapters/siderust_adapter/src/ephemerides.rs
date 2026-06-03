use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::Instant;

use crate::qtty;
use crate::qtty::AstronomicalUnit;

use siderust::astro::eop::NullEop;
use siderust::bodies::solar_system::{
    Jupiter, Mars, Mercury, Moon, Neptune, Saturn, Uranus, Venus,
};
use siderust::coordinates::centers::{Geocentric, Heliocentric};
use siderust::coordinates::frames::ICRS;
use siderust::coordinates::transform::{
    AstroContext, PositionAstroExt, Transform, TransformCenter,
};
use siderust::ephemeris::{
    DynEphemeris, MajorPlanet, PlanetPoint, RuntimeEphemeris, Vsop87Ephemeris, VSOP87,
};
use siderust::event::lunar::meeus_ch47;
use siderust::formats::spice::{SpkKernelError, SpkKernelSet};
use siderust::time::JulianDate;

type HelioEclipticPos =
    siderust::coordinates::cartesian::position::EclipticMeanJ2000<AstronomicalUnit, Heliocentric>;

const KM_PER_AU: f64 = 149_597_870.700;

/// Explicit VSOP87 context — used so that the analytic rows do not silently
/// pick up the cargo-feature-selected default ephemeris (e.g. DE440) for
/// the Heliocentric → Geocentric center shift. Audit fix F3: label honesty.
#[inline]
fn vsop87_ctx() -> AstroContext<Vsop87Ephemeris, NullEop> {
    AstroContext::<Vsop87Ephemeris, NullEop>::with_types()
}

fn planet_ra_dec_dist(
    planet_vsop87a: fn(JulianDate) -> HelioEclipticPos,
    jd: JulianDate,
) -> (f64, f64, f64) {
    let helio = planet_vsop87a(jd);
    // Explicit VSOP87 center shift — do NOT inherit DefaultEphemeris.
    let ctx = vsop87_ctx();
    let geo_ecl: siderust::coordinates::cartesian::position::EclipticMeanJ2000<
        AstronomicalUnit,
        Geocentric,
    > = helio.to_center_with((), jd, &ctx);
    let geo_icrs: siderust::coordinates::cartesian::Position<Geocentric, ICRS, AstronomicalUnit> =
        geo_ecl.to_frame_with(&jd, &ctx);
    let sph = siderust::coordinates::spherical::Position::from_cartesian(&geo_icrs);

    (
        sph.azimuth.value().to_radians(),
        sph.polar.value().to_radians(),
        sph.distance.value(),
    )
}

fn icrf_km_ra_dec_dist(x_km: f64, y_km: f64, z_km: f64) -> (f64, f64, f64) {
    let dist_km = (x_km * x_km + y_km * y_km + z_km * z_km).sqrt();
    let ra_rad = y_km.atan2(x_km).rem_euclid(2.0 * std::f64::consts::PI);
    let dec_rad = (z_km / dist_km).asin();
    (ra_rad, dec_rad, dist_km / KM_PER_AU)
}

#[cfg(feature = "de440")]
fn de440_planet_ra_dec_dist(
    planet: MajorPlanet,
    point: PlanetPoint,
    jd: JulianDate,
) -> Result<(f64, f64, f64), String> {
    let kernels = planet_kernel_set()?;
    spk_planet_ra_dec_dist(kernels, planet, point, jd)
}

fn push_planet_kernel_path(paths: &mut Vec<PathBuf>, path: PathBuf) {
    if path.is_file() && !paths.contains(&path) {
        paths.push(path);
    }
}

fn push_cached_planet_kernel_paths(paths: &mut Vec<PathBuf>, root: &Path) {
    for relative in [
        // Build-time JPL cache layout selected by SIDERUST_DATASETS_DIR.
        "de440_dataset/de440.bsp",
        "de441_dataset/de441_part-2.bsp",
        // Runtime DataManager layout selected by SIDERUST_DATA_DIR.
        "de440.bsp",
        "de441_part-2.bsp",
        // Mars through Neptune center offsets.
        "mar099.bsp",
        "jup365.bsp",
        "jup365_merged.bsp",
        "sat441l.bsp",
        "ura184.bsp",
        "ura184_merged.bsp",
        "nep097.bsp",
    ] {
        push_planet_kernel_path(paths, root.join(relative));
    }
}

fn default_runtime_data_dir() -> Option<PathBuf> {
    if let Some(raw) = std::env::var_os("SIDERUST_DATA_DIR") {
        let path = PathBuf::from(raw);
        if !path.as_os_str().is_empty() {
            return Some(path);
        }
    }

    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(|home| PathBuf::from(home).join(".siderust/data"))
}

fn has_planetary_de_kernel(paths: &[PathBuf]) -> bool {
    paths.iter().any(|path| {
        matches!(
            path.file_name().and_then(|name| name.to_str()),
            Some("de440.bsp" | "de441_part-2.bsp")
        )
    })
}

fn planet_kernel_paths() -> Vec<PathBuf> {
    if let Some(raw) = std::env::var_os("SIDERUST_PLANET_KERNELS") {
        return std::env::split_paths(&raw)
            .filter(|path| path.is_file())
            .collect();
    }

    let mut paths = Vec::new();
    if let Some(datasets_dir) = std::env::var_os("SIDERUST_DATASETS_DIR") {
        push_cached_planet_kernel_paths(&mut paths, &PathBuf::from(datasets_dir));
    }
    if let Some(data_dir) = default_runtime_data_dir() {
        push_cached_planet_kernel_paths(&mut paths, &data_dir);
    }

    let bundled_de440 =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("datasets/de440_dataset/de440.bsp");
    if !has_planetary_de_kernel(&paths) && bundled_de440.is_file() {
        // Satellite kernels supply outer center offsets only. Keep the bundled
        // planetary kernel available for barycenter motion and the Earth chain.
        paths.insert(0, bundled_de440);
    }
    paths
}

fn de_kernel_path() -> Option<PathBuf> {
    planet_kernel_paths().into_iter().find(|path| {
        matches!(
            path.file_name().and_then(|name| name.to_str()),
            Some("de440.bsp" | "de441_part-2.bsp")
        )
    })
}

#[cfg(feature = "de440")]
fn runtime_de_ephemeris() -> Result<&'static RuntimeEphemeris, String> {
    static EPHEMERIS: OnceLock<Result<RuntimeEphemeris, String>> = OnceLock::new();
    EPHEMERIS
        .get_or_init(|| {
            let path = de_kernel_path().ok_or_else(|| {
                "no DE440/DE441 BSP file found; set SIDERUST_PLANET_KERNELS, \
                 SIDERUST_DATASETS_DIR, or SIDERUST_DATA_DIR"
                    .to_string()
            })?;
            RuntimeEphemeris::from_bsp(&path).map_err(|err| {
                format!(
                    "could not load runtime DE ephemeris from {}: {err}",
                    path.display()
                )
            })
        })
        .as_ref()
        .map_err(|err| err.clone())
}

fn build_planet_kernel_set() -> Result<SpkKernelSet, String> {
    let paths = planet_kernel_paths();
    if paths.is_empty() {
        return Err(
            "no SPK files found; set SIDERUST_PLANET_KERNELS to DE440 plus required satellite kernels"
                .to_string(),
        );
    }
    SpkKernelSet::from_paths(&paths)
        .map_err(|err| format!("could not load runtime SPK kernel stack: {err}"))
}

fn planet_kernel_set() -> Result<&'static SpkKernelSet, String> {
    static KERNELS: OnceLock<Result<SpkKernelSet, String>> = OnceLock::new();
    KERNELS
        .get_or_init(build_planet_kernel_set)
        .as_ref()
        .map_err(|err| err.clone())
}

fn spk_planet_ra_dec_dist(
    kernels: &SpkKernelSet,
    planet: MajorPlanet,
    point: PlanetPoint,
    jd: JulianDate,
) -> Result<(f64, f64, f64), String> {
    let state = kernels
        .try_major_planet_geocentric(planet, point, jd)
        .map_err(|err| planet_spk_error(planet, point, err))?;
    Ok(icrf_km_ra_dec_dist(
        state.x().value(),
        state.y().value(),
        state.z().value(),
    ))
}

fn planet_spk_error(planet: MajorPlanet, point: PlanetPoint, err: SpkKernelError) -> String {
    let message = err.to_string();
    if !matches!(point, PlanetPoint::Center)
        || !matches!(err, SpkKernelError::MissingSegment { .. })
    {
        return message;
    }

    let required_kernel = match planet {
        MajorPlanet::Mars => Some("mar099.bsp"),
        MajorPlanet::Jupiter => Some("jup365.bsp"),
        MajorPlanet::Saturn => Some("sat441l.bsp"),
        MajorPlanet::Uranus => Some("ura184.bsp"),
        MajorPlanet::Neptune => Some("nep097.bsp"),
        MajorPlanet::Mercury | MajorPlanet::Venus => None,
    };

    match required_kernel {
        Some(kernel) => format!(
            "{message}; {kernel} is required for this planet-center lane. \
             Add it via SIDERUST_PLANET_KERNELS, SIDERUST_DATASETS_DIR, or SIDERUST_DATA_DIR"
        ),
        None => message,
    }
}

fn emit_planet_skip(experiment: &str, reason: impl Into<String>) {
    println!(
        "{}",
        serde_json::json!({
            "experiment": experiment,
            "library": "siderust",
            "skipped": true,
            "reason": reason.into(),
        })
    );
}

fn emit_perf_skip(experiment: &str, count_requested: usize, reason: impl Into<String>) {
    let reason = reason.into();
    println!(
        "{}",
        serde_json::json!({
            "experiment": format!("{experiment}_perf"),
            "library": "siderust",
            "count_requested": count_requested,
            "count_valid": 0,
            "error_count": count_requested,
            "count": count_requested,
            "valid": false,
            "skipped": true,
            "reason": reason,
        })
    );
}

fn emit_siderust_valid_perf(experiment: &str, library: &str, count: usize, total_ns: f64, sink: f64) {
    let per_op_ns = total_ns / count as f64;
    println!(
        "{}",
        serde_json::json!({
            "experiment": format!("{experiment}_perf"),
            "library": library,
            "count_requested": count,
            "count_valid": count,
            "error_count": 0,
            "count": count,
            "valid": true,
            "skipped": false,
            "total_ns": total_ns,
            "per_op_ns": per_op_ns,
            "throughput_ops_s": count as f64 / (total_ns * 1e-9),
            "_sink": sink,
        })
    );
}

fn read_planet_jds(lines: &mut impl Iterator<Item = String>) -> Vec<f64> {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let mut jds = Vec::with_capacity(n);
    for _ in 0..n {
        jds.push(lines.next().unwrap().trim().parse().unwrap());
    }
    jds
}

fn write_planet_cases(
    experiment: &str,
    model: &str,
    jds: &[f64],
    compute: impl Fn(JulianDate) -> Result<(f64, f64, f64), String>,
) {
    if let Some(first_jd) = jds.first() {
        if let Err(err) = compute(JulianDate::new(*first_jd)) {
            emit_planet_skip(experiment, err);
            return;
        }
    }

    let stdout = io::stdout();
    let mut out = stdout.lock();
    write!(
        out,
        "{{\"experiment\":\"{}\",\"library\":\"siderust\",\
         \"model\":\"{}\",\"count\":{},\"cases\":[\n",
        experiment,
        model,
        jds.len()
    )
    .unwrap();

    for (i, jd_tt) in jds.iter().enumerate() {
        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        match compute(JulianDate::new(*jd_tt)) {
            Ok((ra_rad, dec_rad, dist_au)) => write!(
                out,
                "{{\"jd_tt\":{:.15},\
                 \"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\"dist_au\":{:.17e}}}",
                jd_tt, ra_rad, dec_rad, dist_au,
            )
            .unwrap(),
            Err(_) => write!(
                out,
                "{{\"jd_tt\":{:.15},\"ra_rad\":null,\"dec_rad\":null,\"dist_au\":null}}",
                jd_tt
            )
            .unwrap(),
        }
    }

    writeln!(out, "\n]}}").unwrap();
}

fn solar_ra_dec_dist_vsop87(jd: JulianDate) -> (f64, f64, f64) {
    let helio = siderust::coordinates::cartesian::position::EclipticMeanJ2000::<
        AstronomicalUnit,
        Heliocentric,
    >::CENTER;
    let ctx = vsop87_ctx();
    let geo_ecl: siderust::coordinates::cartesian::position::EclipticMeanJ2000<
        AstronomicalUnit,
        Geocentric,
    > = helio.to_center_with((), jd, &ctx);
    let geo_icrs: siderust::coordinates::cartesian::Position<Geocentric, ICRS, AstronomicalUnit> =
        geo_ecl.to_frame_with(&jd, &ctx);
    let sph = siderust::coordinates::spherical::Position::from_cartesian(&geo_icrs);
    (
        sph.azimuth.value().to_radians(),
        sph.polar.value().to_radians(),
        sph.distance.value(),
    )
}

#[cfg(feature = "de440")]
fn solar_ra_dec_dist_de440(jd: JulianDate) -> (f64, f64, f64) {
    let eph = runtime_de_ephemeris().expect("runtime DE ephemeris unavailable");
    let earth_helio = eph.earth_heliocentric(jd);
    // Negate Earth heliocentric to get Sun geocentric in the same ecliptic frame
    let sun_geo_ecl = siderust::coordinates::cartesian::position::EclipticMeanJ2000::<
        AstronomicalUnit,
        Geocentric,
    >::new(-earth_helio.x(), -earth_helio.y(), -earth_helio.z());
    let geo_icrs: siderust::coordinates::cartesian::Position<Geocentric, ICRS, AstronomicalUnit> =
        sun_geo_ecl.transform(jd);
    let sph = siderust::coordinates::spherical::Position::from_cartesian(&geo_icrs);
    (
        sph.azimuth.value().to_radians(),
        sph.polar.value().to_radians(),
        sph.distance.value(),
    )
}

fn solar_library_and_model() -> (&'static str, &'static str) {
    #[cfg(feature = "de440")]
    if std::env::var("SIDERUST_SOLAR_MODEL").as_deref() == Ok("de440") {
        return ("siderust_de440", "JPL_DE440_geometric");
    }
    ("siderust", "VSOP87_geometric")
}

fn compute_solar_ra_dec_dist(jd: JulianDate) -> (f64, f64, f64) {
    #[cfg(feature = "de440")]
    if std::env::var("SIDERUST_SOLAR_MODEL").as_deref() == Ok("de440") {
        return solar_ra_dec_dist_de440(jd);
    }
    solar_ra_dec_dist_vsop87(jd)
}

fn lunar_ra_dec_dist_meeus(jd: JulianDate) -> (f64, f64, f64) {
    let moon = meeus_ch47::moon_position_meeus_ch47(jd);
    (
        moon.ra.to::<qtty::Radian>().value(),
        moon.dec.to::<qtty::Radian>().value(),
        moon.dist.value(),
    )
}

fn lunar_ra_dec_dist_elp2000(jd: JulianDate) -> (f64, f64, f64) {
    let moon_ecl = Moon::get_geo_position::<qtty::Kilometer>(jd);
    let moon_icrs: siderust::coordinates::cartesian::Position<Geocentric, ICRS, qtty::Kilometer> =
        moon_ecl.transform(jd);
    let sph = siderust::coordinates::spherical::Position::from_cartesian(&moon_icrs);
    (
        sph.azimuth.value().to_radians(),
        sph.polar.value().to_radians(),
        sph.distance.value(),
    )
}

// DE440 lunar path. The upstream De440Ephemeris::moon_geocentric formula
// has been corrected (Moon_geo = moon_off / FRAC_EARTH), so this path now
// produces JPL-grade geocentric Moon positions.
#[cfg(feature = "de440")]
fn lunar_ra_dec_dist_de440(jd: JulianDate) -> (f64, f64, f64) {
    let eph = runtime_de_ephemeris().expect("runtime DE ephemeris unavailable");
    let moon_ecl = eph.moon_geocentric(jd);
    let moon_icrs: siderust::coordinates::cartesian::Position<Geocentric, ICRS, qtty::Kilometer> =
        moon_ecl.transform(jd);
    let sph = siderust::coordinates::spherical::Position::from_cartesian(&moon_icrs);
    (
        sph.azimuth.value().to_radians(),
        sph.polar.value().to_radians(),
        sph.distance.value(),
    )
}

/// Convert a barycentric EclipticMeanJ2000 position (AU) to SSB-relative ICRS RA/Dec/dist.
#[cfg(feature = "de440")]
fn lunar_library_and_model() -> (&'static str, &'static str) {
    let lunar_model = std::env::var("SIDERUST_LUNAR_MODEL").unwrap_or_default();
    match lunar_model.as_str() {
        "elp2000" => ("siderust", "ELP2000-82B"),
        #[cfg(feature = "de440")]
        "de440" => ("siderust_de440", "JPL_DE440_geometric"),
        _ => ("siderust", "Meeus_Ch47_simplified"),
    }
}

fn compute_lunar_ra_dec_dist(jd: JulianDate) -> (f64, f64, f64) {
    let lunar_model = std::env::var("SIDERUST_LUNAR_MODEL").unwrap_or_default();
    if lunar_model == "elp2000" {
        return lunar_ra_dec_dist_elp2000(jd);
    }
    #[cfg(feature = "de440")]
    if lunar_model == "de440" {
        return lunar_ra_dec_dist_de440(jd);
    }
    lunar_ra_dec_dist_meeus(jd)
}

pub(crate) fn run_solar_position(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    let (library, model) = solar_library_and_model();
    write!(
        out,
        "{{\"experiment\":\"solar_position\",\"library\":\"{library}\",\
         \"model\":\"{model}\",\
         \"count\":{n},\"cases\":[\n",
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let jd_tt: f64 = line.trim().parse().unwrap();
        let jd = JulianDate::new(jd_tt);
        let (ra_rad, dec_rad, dist_au) = compute_solar_ra_dec_dist(jd);

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{jd_tt:.15},\
             \"ra_rad\":{ra_rad:.17e},\"dec_rad\":{dec_rad:.17e},\"dist_au\":{dist_au:.17e}}}",
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_lunar_position(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    let (library, model) = lunar_library_and_model();
    write!(
        out,
        "{{\"experiment\":\"lunar_position\",\"library\":\"{library}\",\
         \"model\":\"{model}\",\
         \"count\":{n},\"cases\":[\n",
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let jd_tt: f64 = line.trim().parse().unwrap();
        let (ra_rad, dec_rad, dist_km) = compute_lunar_ra_dec_dist(JulianDate::new(jd_tt));

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{jd_tt:.15},\
             \"ra_rad\":{ra_rad:.17e},\"dec_rad\":{dec_rad:.17e},\"dist_km\":{dist_km:.17e}}}",
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_planet_position(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    model: &str,
    planet_vsop87a: fn(JulianDate) -> HelioEclipticPos,
) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"{}\",\"library\":\"siderust\",\
         \"model\":\"{}\",\"count\":{},\"cases\":[\n",
        experiment, model, n
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let jd_tt: f64 = line.trim().parse().unwrap();
        let (ra_rad, dec_rad, dist_au) = planet_ra_dec_dist(planet_vsop87a, JulianDate::new(jd_tt));

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\
             \"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\"dist_au\":{:.17e}}}",
            jd_tt, ra_rad, dec_rad, dist_au,
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

fn planet_point(experiment: &str) -> PlanetPoint {
    if experiment.contains("_barycenter_") {
        PlanetPoint::SystemBarycenter
    } else {
        PlanetPoint::Center
    }
}

fn run_major_planet_position(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    planet: MajorPlanet,
    planet_vsop87a: fn(JulianDate) -> HelioEclipticPos,
) {
    let point = planet_point(experiment);
    let model = std::env::var("SIDERUST_PLANET_MODEL")
        .unwrap_or_else(|_| "vsop87".to_string())
        .to_ascii_lowercase();

    if model == "vsop87" {
        // VSOP87 always computes the geocentric planet-center position. For
        // *_barycenter_position experiments this is used as a best-available
        // proxy (parity = "analytic"; planet-center ≈ system-barycenter within
        // VSOP87's model error, especially for inner planets).
        run_planet_position(
            lines,
            experiment,
            &format!("siderust_VSOP87A_geometric_{planet:?}").to_ascii_lowercase(),
            planet_vsop87a,
        );
        return;
    }

    let jds = read_planet_jds(lines);
    match model.as_str() {
        "de440_barycenter" => {
            if point != PlanetPoint::SystemBarycenter {
                emit_planet_skip(
                    experiment,
                    "de440_barycenter exposes the planet-system barycenter lane only",
                );
                return;
            }
            #[cfg(feature = "de440")]
            write_planet_cases(experiment, "JPL_DE440_embedded_system_barycenter", &jds, |jd| {
                de440_planet_ra_dec_dist(planet, point, jd)
            });
            #[cfg(not(feature = "de440"))]
            emit_planet_skip(experiment, "adapter was built without the de440 feature");
        }
        "spk_center" | "spk_barycenter" => {
            let configured_point = if model == "spk_center" {
                PlanetPoint::Center
            } else {
                PlanetPoint::SystemBarycenter
            };
            if point != configured_point {
                emit_planet_skip(
                    experiment,
                    format!("{model} does not serve the requested planet lane"),
                );
                return;
            }
            match planet_kernel_set() {
                Ok(kernels) => {
                    let model_label = if point == PlanetPoint::Center {
                        "SPK_runtime_planet_center"
                    } else {
                        "SPK_runtime_system_barycenter"
                    };
                    write_planet_cases(experiment, model_label, &jds, |jd| {
                        spk_planet_ra_dec_dist(kernels, planet, point, jd)
                    });
                }
                Err(err) => emit_planet_skip(experiment, err),
            }
        }
        other => emit_planet_skip(
            experiment,
            format!(
                "unknown SIDERUST_PLANET_MODEL={other}; expected vsop87, de440_barycenter, spk_center, or spk_barycenter"
            ),
        ),
    }
}

pub(crate) fn run_solar_position_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut jds: Vec<f64> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        jds.push(line.trim().parse().unwrap());
    }

    let (library, _model) = solar_library_and_model();

    // Warm-up
    let warmup = crate::perf_warmup();
    for i in 0..n.min(warmup) {
        let (ra, dec, dist) = compute_solar_ra_dec_dist(JulianDate::new(jds[i]));
        std::hint::black_box((ra, dec, dist));
    }

    // Timed run — perf contract: compute RA + Dec + distance
    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for i in 0..n {
        let (ra_rad, dec_rad, dist_au) = compute_solar_ra_dec_dist(JulianDate::new(jds[i]));
        sink += ra_rad + dec_rad + dist_au;
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    emit_siderust_valid_perf("solar_position", library, n, total_ns, sink);
}

pub(crate) fn run_lunar_position_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut jds: Vec<f64> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        jds.push(line.trim().parse().unwrap());
    }

    let (library, _model) = lunar_library_and_model();

    // Warm-up
    let warmup = crate::perf_warmup();
    for i in 0..n.min(warmup) {
        let (ra, dec, dist) = compute_lunar_ra_dec_dist(JulianDate::new(jds[i]));
        std::hint::black_box((ra, dec, dist));
    }

    // Timed run — perf contract: compute RA + Dec + distance
    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for i in 0..n {
        let (ra, dec, dist_km) = compute_lunar_ra_dec_dist(JulianDate::new(jds[i]));
        sink += ra + dec + dist_km;
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    emit_siderust_valid_perf("lunar_position", library, n, total_ns, sink);
}

pub(crate) fn run_planet_position_perf(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    planet_vsop87a: fn(JulianDate) -> HelioEclipticPos,
) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut jds: Vec<f64> = Vec::with_capacity(n);
    for _ in 0..n {
        let line = lines.next().unwrap();
        jds.push(line.trim().parse().unwrap());
    }

    let warmup = crate::perf_warmup();
    for jd_tt in jds.iter().take(n.min(warmup)) {
        let (ra, dec, dist) = planet_ra_dec_dist(planet_vsop87a, JulianDate::new(*jd_tt));
        std::hint::black_box(ra + dec + dist);
    }

    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for jd_tt in &jds {
        let (ra, dec, dist) = planet_ra_dec_dist(planet_vsop87a, JulianDate::new(*jd_tt));
        sink += ra + dec + dist;
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    emit_siderust_valid_perf(experiment, "siderust", n, total_ns, sink);
}

fn run_major_planet_position_perf(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    planet: MajorPlanet,
    planet_vsop87a: fn(JulianDate) -> HelioEclipticPos,
) {
    let point = planet_point(experiment);
    let model = std::env::var("SIDERUST_PLANET_MODEL")
        .unwrap_or_else(|_| "vsop87".to_string())
        .to_ascii_lowercase();
    if model == "vsop87" {
        // VSOP87 planet-center is also the best-available proxy for *_barycenter_position.
        run_planet_position_perf(lines, experiment, planet_vsop87a);
        return;
    }

    let jds = read_planet_jds(lines);
    let n = jds.len();

    #[cfg(feature = "de440")]
    let de440_compute = |jd_tt: f64| de440_planet_ra_dec_dist(planet, point, JulianDate::new(jd_tt));

    match model.as_str() {
        "de440_barycenter" if point == PlanetPoint::SystemBarycenter => {
            #[cfg(feature = "de440")]
            for jd_tt in &jds {
                if let Err(err) = de440_compute(*jd_tt) {
                    emit_perf_skip(experiment, n, err);
                    return;
                }
            }
            #[cfg(not(feature = "de440"))]
            {
                emit_perf_skip(experiment, n, "adapter was built without the de440 feature");
                return;
            }
        }
        "spk_center" | "spk_barycenter" => {
            let configured_point = if model == "spk_center" {
                PlanetPoint::Center
            } else {
                PlanetPoint::SystemBarycenter
            };
            if point != configured_point {
                emit_perf_skip(
                    experiment,
                    n,
                    format!("SIDERUST_PLANET_MODEL={model} does not apply to {experiment}"),
                );
                return;
            }
            let kernels = match planet_kernel_set() {
                Ok(k) => k,
                Err(err) => {
                    emit_perf_skip(experiment, n, err);
                    return;
                }
            };
            for jd_tt in &jds {
                if let Err(err) =
                    spk_planet_ra_dec_dist(kernels, planet, point, JulianDate::new(*jd_tt))
                {
                    emit_perf_skip(experiment, n, err);
                    return;
                }
            }
        }
        other => {
            emit_perf_skip(
                experiment,
                n,
                format!(
                    "unknown SIDERUST_PLANET_MODEL={other}; expected vsop87, de440_barycenter, spk_center, or spk_barycenter"
                ),
            );
            return;
        }
    }

    let compute = |jd_tt: f64| -> (f64, f64, f64) {
        match model.as_str() {
            "de440_barycenter" if point == PlanetPoint::SystemBarycenter => {
                #[cfg(feature = "de440")]
                {
                    de440_compute(jd_tt).expect("preflight guaranteed success")
                }
                #[cfg(not(feature = "de440"))]
                unreachable!()
            }
            "spk_center" | "spk_barycenter" => {
                let kernels = planet_kernel_set().expect("preflight guaranteed success");
                spk_planet_ra_dec_dist(kernels, planet, point, JulianDate::new(jd_tt))
                    .expect("preflight guaranteed success")
            }
            _ => unreachable!(),
        }
    };

    let warmup = crate::perf_warmup();
    for jd_tt in jds.iter().take(n.min(warmup)) {
        let (ra, dec, dist) = compute(*jd_tt);
        std::hint::black_box(ra + dec + dist);
    }

    let start = Instant::now();
    let mut sink = 0.0_f64;
    for jd_tt in &jds {
        let (ra, dec, dist) = compute(*jd_tt);
        sink += ra + dec + dist;
    }
    let total_ns = start.elapsed().as_nanos() as f64;
    emit_siderust_valid_perf(experiment, "siderust", n, total_ns, sink);
}

pub(crate) fn run_mercury_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "mercury_position", MajorPlanet::Mercury, |jd| {
        Mercury.vsop87a(jd)
    });
}

pub(crate) fn run_venus_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "venus_position", MajorPlanet::Venus, |jd| {
        Venus.vsop87a(jd)
    });
}

pub(crate) fn run_mars_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "mars_position", MajorPlanet::Mars, |jd| {
        Mars.vsop87a(jd)
    });
}

pub(crate) fn run_jupiter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "jupiter_position", MajorPlanet::Jupiter, |jd| {
        Jupiter.vsop87a(jd)
    });
}

pub(crate) fn run_saturn_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "saturn_position", MajorPlanet::Saturn, |jd| {
        Saturn.vsop87a(jd)
    });
}

pub(crate) fn run_uranus_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "uranus_position", MajorPlanet::Uranus, |jd| {
        let ctx = vsop87_ctx();
        Uranus.vsop87e(jd).to_center_with((), jd, &ctx)
    });
}

pub(crate) fn run_neptune_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "neptune_position", MajorPlanet::Neptune, |jd| {
        let ctx = vsop87_ctx();
        Neptune.vsop87e(jd).to_center_with((), jd, &ctx)
    });
}

pub(crate) fn run_mercury_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "mercury_barycenter_position",
        MajorPlanet::Mercury,
        |jd| Mercury.vsop87a(jd),
    );
}

pub(crate) fn run_venus_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "venus_barycenter_position",
        MajorPlanet::Venus,
        |jd| Venus.vsop87a(jd),
    );
}

pub(crate) fn run_mars_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(lines, "mars_barycenter_position", MajorPlanet::Mars, |jd| {
        Mars.vsop87a(jd)
    });
}

pub(crate) fn run_jupiter_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "jupiter_barycenter_position",
        MajorPlanet::Jupiter,
        |jd| Jupiter.vsop87a(jd),
    );
}

pub(crate) fn run_saturn_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "saturn_barycenter_position",
        MajorPlanet::Saturn,
        |jd| Saturn.vsop87a(jd),
    );
}

pub(crate) fn run_uranus_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "uranus_barycenter_position",
        MajorPlanet::Uranus,
        |jd| {
            let ctx = vsop87_ctx();
            Uranus.vsop87e(jd).to_center_with((), jd, &ctx)
        },
    );
}

pub(crate) fn run_neptune_barycenter_position(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position(
        lines,
        "neptune_barycenter_position",
        MajorPlanet::Neptune,
        |jd| {
            let ctx = vsop87_ctx();
            Neptune.vsop87e(jd).to_center_with((), jd, &ctx)
        },
    );
}

pub(crate) fn run_mercury_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "mercury_position", MajorPlanet::Mercury, |jd| {
        Mercury.vsop87a(jd)
    });
}

pub(crate) fn run_venus_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "venus_position", MajorPlanet::Venus, |jd| {
        Venus.vsop87a(jd)
    });
}

pub(crate) fn run_mars_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "mars_position", MajorPlanet::Mars, |jd| {
        Mars.vsop87a(jd)
    });
}

pub(crate) fn run_jupiter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "jupiter_position", MajorPlanet::Jupiter, |jd| {
        Jupiter.vsop87a(jd)
    });
}

pub(crate) fn run_saturn_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "saturn_position", MajorPlanet::Saturn, |jd| {
        Saturn.vsop87a(jd)
    });
}

pub(crate) fn run_uranus_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "uranus_position", MajorPlanet::Uranus, |jd| {
        let ctx = vsop87_ctx();
        Uranus.vsop87e(jd).to_center_with((), jd, &ctx)
    });
}

pub(crate) fn run_neptune_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "neptune_position", MajorPlanet::Neptune, |jd| {
        let ctx = vsop87_ctx();
        Neptune.vsop87e(jd).to_center_with((), jd, &ctx)
    });
}

pub(crate) fn run_mercury_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "mercury_barycenter_position",
        MajorPlanet::Mercury,
        |jd| Mercury.vsop87a(jd),
    );
}

pub(crate) fn run_venus_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "venus_barycenter_position",
        MajorPlanet::Venus,
        |jd| Venus.vsop87a(jd),
    );
}

pub(crate) fn run_mars_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(lines, "mars_barycenter_position", MajorPlanet::Mars, |jd| {
        Mars.vsop87a(jd)
    });
}

pub(crate) fn run_jupiter_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "jupiter_barycenter_position",
        MajorPlanet::Jupiter,
        |jd| Jupiter.vsop87a(jd),
    );
}

pub(crate) fn run_saturn_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "saturn_barycenter_position",
        MajorPlanet::Saturn,
        |jd| Saturn.vsop87a(jd),
    );
}

pub(crate) fn run_uranus_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "uranus_barycenter_position",
        MajorPlanet::Uranus,
        |jd| {
            let ctx = vsop87_ctx();
            Uranus.vsop87e(jd).to_center_with((), jd, &ctx)
        },
    );
}

pub(crate) fn run_neptune_barycenter_position_perf(lines: &mut impl Iterator<Item = String>) {
    run_major_planet_position_perf(
        lines,
        "neptune_barycenter_position",
        MajorPlanet::Neptune,
        |jd| {
            let ctx = vsop87_ctx();
            Neptune.vsop87e(jd).to_center_with((), jd, &ctx)
        },
    );
}

pub(crate) fn run_setup(experiment: &str) {
    let base = experiment.strip_suffix("_setup").unwrap_or(experiment);
    let mut setup_ms = 0.0_f64;
    let mut measured = true;

    #[cfg(feature = "de440")]
    if base == "solar_position" && std::env::var("SIDERUST_SOLAR_MODEL").as_deref() == Ok("de440") {
        let start = Instant::now();
        let (ra, dec, dist) = compute_solar_ra_dec_dist(JulianDate::new(2451545.0));
        std::hint::black_box((ra, dec, dist));
        setup_ms = start.elapsed().as_secs_f64() * 1000.0;
        measured = true;
    }

    #[cfg(feature = "de440")]
    if base == "lunar_position" && std::env::var("SIDERUST_LUNAR_MODEL").as_deref() == Ok("de440") {
        let start = Instant::now();
        let (ra, dec, dist) = compute_lunar_ra_dec_dist(JulianDate::new(2451545.0));
        std::hint::black_box((ra, dec, dist));
        setup_ms = start.elapsed().as_secs_f64() * 1000.0;
        measured = true;
    }

    println!(
        "{{\"setup_ms\":{:.6},\"measured\":{}}}",
        setup_ms,
        if measured { "true" } else { "false" }
    );
}
