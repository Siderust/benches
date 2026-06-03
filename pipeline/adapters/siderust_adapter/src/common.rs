pub mod qtty {
    pub use qtty_crate::unit::{AstronomicalUnit, Degree, Kilometer, Meter, Radian};
    pub use qtty_crate::{Quantity, RAD};

    pub type Degrees<S = f64> = Quantity<Degree, S>;
    pub type Meters<S = f64> = Quantity<Meter, S>;
    pub type Radians<S = f64> = Quantity<Radian, S>;
}

pub mod affn {
    pub use affn_crate::Rotation3;

    pub mod cartesian {
        pub use affn_crate::cartesian::*;
    }

    pub mod spherical {
        use std::ops::Deref;

        #[repr(transparent)]
        #[derive(Debug, Clone, Copy)]
        pub struct Direction<F: affn_crate::frames::ReferenceFrame>(
            affn_crate::spherical::Direction<F>,
        );

        impl<F: affn_crate::frames::ReferenceFrame> Direction<F> {
            pub const fn new_raw(
                polar: crate::qtty::Degrees,
                azimuth: crate::qtty::Degrees,
            ) -> Self {
                Self(affn_crate::spherical::Direction::new_unchecked(
                    polar, azimuth,
                ))
            }
        }

        impl<F: affn_crate::frames::ReferenceFrame> Deref for Direction<F> {
            type Target = affn_crate::spherical::Direction<F>;

            fn deref(&self) -> &Self::Target {
                &self.0
            }
        }

        impl<F: affn_crate::frames::ReferenceFrame> From<affn_crate::spherical::Direction<F>>
            for Direction<F>
        {
            fn from(direction: affn_crate::spherical::Direction<F>) -> Self {
                Self(direction)
            }
        }

        impl<F: affn_crate::frames::ReferenceFrame> From<Direction<F>>
            for affn_crate::spherical::Direction<F>
        {
            fn from(direction: Direction<F>) -> Self {
                direction.0
            }
        }
    }
}

pub(crate) trait CartesianDirectionCompat {
    fn as_vec3(&self) -> [f64; 3];
}

impl<F: affn_crate::frames::ReferenceFrame> CartesianDirectionCompat
    for affn_crate::cartesian::Direction<F>
{
    fn as_vec3(&self) -> [f64; 3] {
        self.as_array()
    }
}

use siderust::astro::eop::EopProvider;
use siderust::astro::nutation::{Iau2000A, Iau2000B, Iau2006, Iau2006A, NutationModel};
use siderust::astro::precession::precession_nutation_matrix;
use siderust::coordinates::transform::providers::{frame_rotation_as, FrameRotationProvider};
use siderust::coordinates::transform::AstroContext;
use siderust::time::JulianDate;

pub(crate) fn ang_sep(a: &[f64; 3], b: &[f64; 3]) -> f64 {
    let dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    dot.clamp(-1.0, 1.0).acos()
}

pub(crate) fn normalize3(v: [f64; 3]) -> [f64; 3] {
    let n = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    [v[0] / n, v[1] / n, v[2] / n]
}

pub(crate) fn selected_nutation_profile() -> String {
    std::env::var("SIDERUST_NUTATION_PROFILE")
        .or_else(|_| std::env::var("SIDERUST_NUTATION"))
        .unwrap_or_else(|_| "iau2006a".to_string())
        .to_ascii_lowercase()
}

pub(crate) fn frame_rotation_selected<F1, F2, Eph, Eop>(
    jd: JulianDate,
    ctx: &AstroContext<Eph, Eop>,
) -> affn::Rotation3
where
    Eop: EopProvider,
    (): FrameRotationProvider<F1, F2>,
{
    match selected_nutation_profile().as_str() {
        "iau2000a" => frame_rotation_as::<F1, F2, Iau2000A, _, _>(jd, ctx),
        "iau2000b" => frame_rotation_as::<F1, F2, Iau2000B, _, _>(jd, ctx),
        "precession_only" => frame_rotation_as::<F1, F2, Iau2006, _, _>(jd, ctx),
        _ => frame_rotation_as::<F1, F2, Iau2006A, _, _>(jd, ctx),
    }
}

/// Pure-IAU BPN matrix (ICRS → True of Date) with no Earth-orientation
/// corrections.
///
/// Built by feeding the selected nutation model's (Δψ, Δε) directly into
/// [`precession_nutation_matrix`], which already composes frame-bias ×
/// precession × nutation. This bypasses `AstroContext::eop_at_tt`, which in
/// the vendored crate unconditionally performs a TT→UTC conversion using
/// `with_builtin_eop()` — that conversion is restricted to the bundled IERS
/// finals horizon and panics on epochs outside ~1962–2030 even when the
/// caller uses [`NullEop`]. Going through the matrix builder keeps the BPN
/// experiment pure-model and lets Siderust be ranked at far-future / deep
/// past epochs.
pub(crate) fn pure_bpn_matrix(jd: JulianDate) -> affn::Rotation3 {
    let nut = match selected_nutation_profile().as_str() {
        "iau2000a" => <Iau2000A as NutationModel>::nutation(jd),
        "iau2000b" => <Iau2000B as NutationModel>::nutation(jd),
        "precession_only" => <Iau2006 as NutationModel>::nutation(jd),
        _ => <Iau2006A as NutationModel>::nutation(jd),
    };
    precession_nutation_matrix(jd, nut.dpsi, nut.deps)
}
