//! Convergence tests for the matrix-free Newton-CG (Steihaug) method.

use approx::assert_relative_eq;
use faer::MatMut;
use spectrafit_types::CoreError;

use crate::{minimize, TrustRegionConfig, TrustRegionProblem};

/// Linear residual `r(x) = A·x − b`, constant Jacobian `J = A`.
struct LinearProblem {
    a: Vec<Vec<f64>>,
    b: Vec<f64>,
    x: Vec<f64>,
}

impl TrustRegionProblem for LinearProblem {
    fn n_residuals(&self) -> usize {
        self.a.len()
    }
    fn n_params(&self) -> usize {
        self.x.len()
    }
    fn params(&self) -> Vec<f64> {
        self.x.clone()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.x.copy_from_slice(p);
    }
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, row) in self.a.iter().enumerate() {
            let dot: f64 = row.iter().zip(&self.x).map(|(a, x)| a * x).sum();
            r[(i, 0)] = dot - self.b[i];
        }
        Ok(())
    }
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, row) in self.a.iter().enumerate() {
            for (jx, &v) in row.iter().enumerate() {
                jac[(i, jx)] = v;
            }
        }
        Ok(())
    }
}

/// Rosenbrock as least squares: `r₁ = 10(x₂ − x₁²)`, `r₂ = 1 − x₁`; min at (1,1).
struct RosenbrockProblem {
    x: [f64; 2],
}

impl TrustRegionProblem for RosenbrockProblem {
    fn n_residuals(&self) -> usize {
        2
    }
    fn n_params(&self) -> usize {
        2
    }
    fn params(&self) -> Vec<f64> {
        self.x.to_vec()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.x = [p[0], p[1]];
    }
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        r[(0, 0)] = 10.0 * (self.x[1] - self.x[0] * self.x[0]);
        r[(1, 0)] = 1.0 - self.x[0];
        Ok(())
    }
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        jac[(0, 0)] = -20.0 * self.x[0];
        jac[(0, 1)] = 10.0;
        jac[(1, 0)] = -1.0;
        jac[(1, 1)] = 0.0;
        Ok(())
    }
}

#[test]
fn newton_cg_recovers_linear_least_squares() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let true_x = [2.0, -1.0];
    let b: Vec<f64> = a
        .iter()
        .map(|row| row[0] * true_x[0] + row[1] * true_x[1])
        .collect();
    let mut prob = LinearProblem {
        a,
        b,
        x: vec![0.0, 0.0],
    };
    let report = minimize(&mut prob, &TrustRegionConfig::default());
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 2.0, epsilon = 1e-7);
    assert_relative_eq!(prob.x[1], -1.0, epsilon = 1e-7);
    assert!(report.cost < 1e-14, "cost = {}", report.cost);
}

#[test]
fn newton_cg_converges_on_rosenbrock() {
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &TrustRegionConfig::default());
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-5);
    assert_relative_eq!(prob.x[1], 1.0, epsilon = 1e-5);
    assert!(report.cost < 1e-10, "cost = {}", report.cost);
}

#[test]
fn newton_cg_recovers_larger_linear_system() {
    // 8 residuals, 5 params: exercises multiple CG inner iterations per step.
    // A[i][j] = 1/(i+j+1) (a Hilbert-like, mildly ill-conditioned block) + a
    // diagonal bump to keep it well-posed.
    let m = 8usize;
    let n = 5usize;
    let a: Vec<Vec<f64>> = (0..m)
        .map(|i| {
            (0..n)
                .map(|j| 1.0 / ((i + j + 1) as f64) + if i == j { 1.0 } else { 0.0 })
                .collect()
        })
        .collect();
    let true_x = vec![1.0, -2.0, 0.5, 3.0, -1.5];
    let b: Vec<f64> = a
        .iter()
        .map(|row| row.iter().zip(&true_x).map(|(a, x)| a * x).sum())
        .collect();
    let mut prob = LinearProblem {
        a,
        b,
        x: vec![0.0; n],
    };
    let report = minimize(&mut prob, &TrustRegionConfig::default());
    assert!(report.termination.was_successful(), "{:?}", report);
    for (i, &t) in true_x.iter().enumerate() {
        assert_relative_eq!(prob.x[i], t, epsilon = 1e-5);
    }
}
