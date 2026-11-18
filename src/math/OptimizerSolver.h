#ifndef OPTIMIZER_SOLVER_H
#define OPTIMIZER_SOLVER_H

#include <functional>
#include <vector>

namespace Optimizer {

/// Result of a Nelder-Mead run.
/// All coordinates are in the normalized [0,1] space the caller works in.
struct Result
{
    std::vector<double> x;   ///< Best point found (normalized coordinates).
    double merit = 0.0;      ///< Merit value at the best point.
    int iterations = 0;      ///< Number of simplex iterations performed.
    int evaluations = 0;     ///< Number of merit function evaluations.
    int restarts = 0;        ///< Number of stagnation restarts performed.
    bool converged = false;  ///< Stopped because both convergence criteria were met.
    bool stopped = false;    ///< Stopped because *stopFlag became true.
};

using MeritFunc = std::function<double(const std::vector<double>&)>;

/// Nelder-Mead simplex minimization with bound handling by variable
/// transformation: the normalized coordinate x in [0,1] is mapped from an
/// unconstrained variable u as x = 0.5 + 0.5*sin(u), and a standard
/// Nelder-Mead runs in the unconstrained u-space.
///
/// A hard clamp of out-of-range vertices would make simplex vertices
/// coplanar or coincident and destroy the simplex; the sin mapping keeps
/// every vertex strictly inside (0,1) with a smooth, differentiable
/// correspondence. Coefficients are the standard ones: alpha=1
/// (reflection), gamma=2 (expansion), rho=0.5 (contraction), sigma=0.5
/// (shrink). The initial simplex uses a Spendley/Gao-Han adaptive step of
/// 0.20 (negative direction when x0[i] > 0.8, to avoid starting on the
/// boundary).
///
/// Convergence requires BOTH criteria at once: the largest simplex edge
/// (in u-space) is smaller than 1e-5 AND f_worst - f_best is smaller than
/// 1e-9. If the best value does not improve by at least 1e-8 for 50
/// consecutive iterations, the simplex is reset once at the current best
/// point with a step of 0.02 (at most 3 restarts), guarding against false
/// convergence. The search also stops when iterations reach maxIter or
/// when *stopFlag becomes true (stopFlag may be null).
///
/// The algorithm is fully deterministic: no random numbers.
Result nelderMead(const MeritFunc& f, const std::vector<double>& x0,
                  int maxIter, const bool* stopFlag = nullptr);

} // namespace Optimizer

#endif // OPTIMIZER_SOLVER_H
