#include "OptimizerSolver.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace Optimizer {

namespace {

constexpr double ALPHA = 1.0;  // reflection
constexpr double GAMMA = 2.0;  // expansion
constexpr double RHO = 0.5;    // contraction
constexpr double SIGMA = 0.5;  // shrink
constexpr double INIT_STEP = 0.20;
constexpr double RESTART_STEP = 0.02;
constexpr double EDGE_TOL = 1e-5;
constexpr double SPREAD_TOL = 1e-9;
constexpr double STAGNATION_IMPROVEMENT = 1e-8;
constexpr int STAGNATION_LIMIT = 50;
constexpr int MAX_RESTARTS = 3;

double clamp01(double v)
{
    return std::max(0.0, std::min(1.0, v));
}

// Normalized coordinate x in [0,1] <-> unconstrained variable u.
double toU(double x)
{
    return std::asin(2.0 * clamp01(x) - 1.0);
}

double toX(double u)
{
    return 0.5 + 0.5 * std::sin(u);
}

double maxEdge(const std::vector<std::vector<double>>& simplex)
{
    double maxEdge = 0.0;
    const auto& best = simplex.front();
    for (size_t i = 1; i < simplex.size(); i++)
    {
        double d2 = 0.0;
        for (size_t j = 0; j < best.size(); j++)
        {
            double d = simplex[i][j] - best[j];
            d2 += d * d;
        }
        maxEdge = std::max(maxEdge, std::sqrt(d2));
    }
    return maxEdge;
}

} // namespace

Result nelderMead(const MeritFunc& f, const std::vector<double>& x0,
                  int maxIter, const bool* stopFlag)
{
    Result res;
    const size_t n = x0.size();
    if (n == 0 || maxIter <= 0)
        return res;

    // Merit function in the unconstrained u-space.
    auto evalU = [&](const std::vector<double>& u) -> double {
        std::vector<double> x(n);
        for (size_t i = 0; i < n; i++)
            x[i] = toX(u[i]);
        res.evaluations++;
        return f(x);
    };

    // Initial simplex in u-space: u0 plus one step along each axis.
    // Step goes negative when x0 is close to the upper boundary, so the
    // simplex does not start pressed against the boundary.
    std::vector<double> u0(n);
    for (size_t i = 0; i < n; i++)
        u0[i] = toU(x0[i]);

    auto buildSimplex = [&](const std::vector<double>& center, double step, bool useDirectionRule) {
        std::vector<std::vector<double>> simplex;
        simplex.reserve(n + 1);
        simplex.push_back(center);
        for (size_t i = 0; i < n; i++)
        {
            auto ui = center;
            // Initial simplex: step away from the upper boundary when the
            // start point is close to it. Restarts always step positive.
            double s = (useDirectionRule && toX(center[i]) > 0.8) ? -step : step;
            ui[i] += s;
            simplex.push_back(ui);
        }
        return simplex;
    };

    std::vector<std::vector<double>> simplex = buildSimplex(u0, INIT_STEP, true);
    std::vector<double> fvals(simplex.size());
    for (size_t i = 0; i < simplex.size(); i++)
        fvals[i] = evalU(simplex[i]);

    auto sortSimplex = [&]() {
        std::vector<size_t> idx(simplex.size());
        for (size_t i = 0; i < idx.size(); i++) idx[i] = i;
        std::sort(idx.begin(), idx.end(), [&](size_t a, size_t b) { return fvals[a] < fvals[b]; });
        std::vector<std::vector<double>> s2;
        std::vector<double> f2;
        for (auto i : idx) { s2.push_back(simplex[i]); f2.push_back(fvals[i]); }
        simplex = s2;
        fvals = f2;
    };

    sortSimplex();

    double bestF = fvals.front();
    int stagnant = 0;

    while (res.iterations < maxIter)
    {
        if (stopFlag && *stopFlag)
        {
            res.stopped = true;
            break;
        }
        // Dual convergence criterion: small simplex AND small merit spread.
        if (maxEdge(simplex) < EDGE_TOL && (fvals.back() - fvals.front()) < SPREAD_TOL)
        {
            res.converged = true;
            break;
        }
        // Stagnation restart: no meaningful improvement for a long while.
        if (stagnant >= STAGNATION_LIMIT && res.restarts < MAX_RESTARTS)
        {
            res.restarts++;
            simplex = buildSimplex(simplex.front(), RESTART_STEP, false);
            for (size_t i = 0; i < simplex.size(); i++)
                fvals[i] = evalU(simplex[i]);
            sortSimplex();
            bestF = fvals.front();
            stagnant = 0;
            continue;
        }
        res.iterations++;

        // Centroid of all vertices except the worst one.
        std::vector<double> centroid(n, 0.0);
        for (size_t i = 0; i < n; i++)
            for (size_t j = 0; j < n; j++)
                centroid[j] += simplex[i][j] / double(n);

        const auto& worst = simplex.back();

        // Reflection.
        std::vector<double> xr(n);
        for (size_t j = 0; j < n; j++)
            xr[j] = centroid[j] + ALPHA * (centroid[j] - worst[j]);
        double fr = evalU(xr);

        if (fr < fvals.front())
        {
            // Expansion.
            std::vector<double> xe(n);
            for (size_t j = 0; j < n; j++)
                xe[j] = centroid[j] + GAMMA * (xr[j] - centroid[j]);
            double fe = evalU(xe);
            if (fe < fr)
            {
                simplex.back() = xe;
                fvals.back() = fe;
            }
            else
            {
                simplex.back() = xr;
                fvals.back() = fr;
            }
        }
        else if (fr < fvals[n - 1])
        {
            simplex.back() = xr;
            fvals.back() = fr;
        }
        else
        {
            // Contraction.
            std::vector<double> xc(n);
            if (fr < fvals.back())
            {
                // Outside contraction.
                for (size_t j = 0; j < n; j++)
                    xc[j] = centroid[j] + RHO * (xr[j] - centroid[j]);
            }
            else
            {
                // Inside contraction.
                for (size_t j = 0; j < n; j++)
                    xc[j] = centroid[j] + RHO * (worst[j] - centroid[j]);
            }
            double fc = evalU(xc);
            if (fc < std::min(fr, fvals.back()))
            {
                simplex.back() = xc;
                fvals.back() = fc;
            }
            else
            {
                // Shrink towards the best vertex.
                for (size_t i = 1; i < simplex.size(); i++)
                {
                    for (size_t j = 0; j < n; j++)
                        simplex[i][j] = simplex.front()[j] + SIGMA * (simplex[i][j] - simplex.front()[j]);
                    fvals[i] = evalU(simplex[i]);
                }
            }
        }

        sortSimplex();

        if (bestF - fvals.front() >= STAGNATION_IMPROVEMENT)
        {
            bestF = fvals.front();
            stagnant = 0;
        }
        else
        {
            stagnant++;
        }
    }

    res.x.resize(n);
    for (size_t i = 0; i < n; i++)
        res.x[i] = toX(simplex.front()[i]);
    res.merit = fvals.front();
    return res;
}

} // namespace Optimizer
