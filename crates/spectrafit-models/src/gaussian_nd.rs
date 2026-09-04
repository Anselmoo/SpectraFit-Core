//! N-dimensional axis-aligned Gaussian kernel (SP-2).
//!
//! A single parametric kernel for any dimensionality `D`, carrying `d` as a
//! field (set at construction from the node's explicit `n_dims`). Generalizes
//! the validated 3-D spike over `0..D` axes. Axis-aligned (no rotation).

use std::borrow::Cow;

use crate::Model;

/// Axis-aligned `D`-dimensional Gaussian peak (`n_dims() == d`).
///
/// `f(x) = A · exp( −Σ_{i=0}^{D-1} (x_i − center_i)² / (2·σ_i²) )`
///
/// Parameters (in order): `[amplitude, center_0 … center_{D-1}, sigma_0 … sigma_{D-1}]`
/// — length `1 + 2D`. Indexed (not `x/y/z`) so the naming scales to arbitrary N.
pub struct GaussianND {
    /// Number of coordinate dimensions.
    d: usize,
}

impl GaussianND {
    /// Construct a `D`-dimensional Gaussian. `d` comes from the node's explicit
    /// `n_dims` field (the compiler passes it in).
    pub fn new(d: usize) -> Self {
        GaussianND { d }
    }
}

impl Model for GaussianND {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let d = self.d;
        let a = params[0];
        let mut z = 0.0_f64;
        for i in 0..d {
            let dx = x[i] - params[1 + i];
            let s = params[1 + d + i];
            z -= (dx * dx) / (2.0 * s * s);
        }
        a * z.exp()
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0_f64; 1 + 2 * self.d];
        self.jacobian_into(x, params, &mut out);
        out
    }

    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let d = self.d;
        let a = params[0];
        // Shared exponential factor g = exp(Σ …).
        let mut z = 0.0_f64;
        for i in 0..d {
            let dx = x[i] - params[1 + i];
            let s = params[1 + d + i];
            z -= (dx * dx) / (2.0 * s * s);
        }
        let g = z.exp();

        out[0] = g; // ∂/∂amplitude
        for i in 0..d {
            let dx = x[i] - params[1 + i];
            let s = params[1 + d + i];
            let s2 = s * s;
            out[1 + i] = a * g * dx / s2; // ∂/∂center_i
            out[1 + d + i] = a * g * dx * dx / (s2 * s); // ∂/∂sigma_i
        }
    }

    fn param_names(&self) -> Vec<Cow<'static, str>> {
        let mut names: Vec<Cow<'static, str>> = Vec::with_capacity(1 + 2 * self.d);
        names.push(Cow::Borrowed("amplitude"));
        for i in 0..self.d {
            names.push(Cow::Owned(format!("center_{i}")));
        }
        for i in 0..self.d {
            names.push(Cow::Owned(format!("sigma_{i}")));
        }
        names
    }

    fn n_dims(&self) -> usize {
        self.d
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn param_names_indexed_and_sized() {
        let m = GaussianND::new(3);
        let names: Vec<String> = m.param_names().iter().map(|c| c.to_string()).collect();
        assert_eq!(
            names,
            vec![
                "amplitude",
                "center_0",
                "center_1",
                "center_2",
                "sigma_0",
                "sigma_1",
                "sigma_2"
            ]
        );
        assert_eq!(m.n_dims(), 3);
    }

    #[test]
    fn eval_at_center_equals_amplitude() {
        let m = GaussianND::new(2);
        // params: A, c0, c1, s0, s1
        let v = m.eval(&[0.5, -1.0], &[3.0, 0.5, -1.0, 1.0, 2.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_into_matches_finite_difference_5d() {
        // Upgraded from a single-point forward difference (h=1e-6,
        // epsilon=1e-4) to a central difference (O(h^2)) swept over three
        // parameter regimes and several x-points relative to each regime's
        // own centre.
        let m = GaussianND::new(5);
        // A, c0..c4, s0..s4
        let param_sets = [
            [2.0, 0.5, -1.0, 1.0, -0.5, 0.3, 1.0, 1.5, 0.9, 1.2, 0.8], // nominal
            [1e-3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05, 0.05, 0.05, 0.05], // small amplitude/width
            [5.0, -2.0, 3.0, -1.5, 2.5, -0.5, 2.0, 3.0, 1.5, 2.5, 1.0], // offset centres, wide
        ];
        let offsets: [[f64; 5]; 3] = [
            [0.0, 0.0, 0.0, 0.0, 0.0],    // at centre
            [0.7, -0.3, 1.1, -0.8, 0.2],  // off-centre (original point)
            [-2.5, 2.0, -1.5, 2.5, -2.0], // far off-centre / near a few sigma
        ];
        for params in param_sets {
            let centers: [f64; 5] = std::array::from_fn(|i| params[1 + i]);
            for off in offsets {
                let x: [f64; 5] = std::array::from_fn(|i| centers[i] + off[i]);
                let mut analytic = vec![0.0_f64; params.len()];
                m.jacobian_into(&x, &params, &mut analytic);
                for i in 0..params.len() {
                    let h = 1e-6 * params[i].abs().max(1.0);
                    let (mut a, mut b) = (params, params);
                    a[i] += h;
                    b[i] -= h;
                    let fd = (m.eval(&x, &a) - m.eval(&x, &b)) / (2.0 * h);
                    assert_relative_eq!(analytic[i], fd, epsilon = 1e-7, max_relative = 1e-6);
                }
            }
        }
    }
}
