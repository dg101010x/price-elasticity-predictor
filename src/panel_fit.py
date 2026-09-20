"""
The estimators behind the external benchmarks in src/build_benchmarks.py.

src/build_elasticity_model.py fits one thing one way: a single-regressor
within-SKU log-log slope on the UCI panel. The reference datasets need more
than that -- some are two-way panels, some come with a genuine instrument,
and the brand-choice scanner panels aren't quantity data at all -- so the
shared machinery lives here rather than being duplicated per dataset.

What's here, and why each one earns its place:

  ols()                 plain/​clustered OLS. Cluster-robust standard errors
                        are the default for panels: repeated observations on
                        the same store or state are not independent draws,
                        and classical SEs on panel data are optimistic by a
                        factor of several.
  within()              absorbs one or two fixed-effect dimensions by
                        alternating projections (the Frisch-Waugh trick used
                        by every serious panel package). Two-way FE on a
                        100k-row panel would otherwise need a 100k x 1000
                        dummy matrix.
  tsls()                two-stage least squares. Price is not randomly
                        assigned in any of these datasets; where an
                        instrument exists -- a cigarette tax, a storm at sea,
                        a cartel collapse -- it is the difference between a
                        correlation and something closer to a demand curve.
  conditional_logit()   McFadden choice model for the household scanner
                        panels, where the observation is "which brand did
                        this shopper pick", not "how many units sold".

Everything returns plain dicts so build_benchmarks.py can serialise them
without a translation layer.
"""

from __future__ import annotations

import numpy as np

# Two-sided 95% normal critical value -- the same one
# src/build_elasticity_model.py uses, kept identical on purpose so the
# benchmark intervals mean the same thing as the headline ones.
Z95 = 1.96


def _as_2d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return x.reshape(-1, 1) if x.ndim == 1 else x


def within(arrays: list[np.ndarray], groups: list[np.ndarray],
           tol: float = 1e-10, max_iter: int = 200) -> list[np.ndarray]:
    """Demean every array by every grouping, simultaneously.

    One grouping is a single pass. Two or more are not separable -- demeaning
    by store undoes part of the demeaning by week -- so the projections are
    alternated to convergence. On a balanced panel this converges in a
    handful of sweeps; the iteration cap is a safety net, not a design.
    """
    out = [np.asarray(a, dtype=float).copy() for a in arrays]
    codes = [np.unique(g, return_inverse=True)[1] for g in groups]
    sizes = [int(c.max()) + 1 for c in codes]

    if len(codes) == 1:
        code, size = codes[0], sizes[0]
        counts = np.bincount(code, minlength=size)
        for a in out:
            a -= (np.bincount(code, weights=a, minlength=size) / counts)[code]
        return out

    counts = [np.bincount(c, minlength=s) for c, s in zip(codes, sizes)]
    for a in out:
        for _ in range(max_iter):
            largest = 0.0
            for code, size, count in zip(codes, sizes, counts):
                means = np.bincount(code, weights=a, minlength=size) / count
                shift = means[code]
                largest = max(largest, float(np.abs(shift).max()))
                a -= shift
            if largest < tol:
                break
    return out


def ols(y: np.ndarray, X: np.ndarray, cluster: np.ndarray | None = None,
        absorbed: int = 0, add_const: bool = True) -> dict:
    """OLS with optional cluster-robust standard errors.

    `absorbed` is how many parameters were removed by within() before the
    call; they cost degrees of freedom even though they never appear in X.
    Ignoring that inflates precision on exactly the panels where precision
    is already the weakest claim.
    """
    y = np.asarray(y, dtype=float).ravel()
    X = _as_2d(X)
    if add_const:
        X = np.column_stack([np.ones(len(y)), X])

    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    dof = max(n - k - absorbed, 1)

    if cluster is None:
        sigma2 = float(resid @ resid) / dof
        vcov = sigma2 * xtx_inv
        n_clusters = None
    else:
        codes = np.unique(np.asarray(cluster), return_inverse=True)[1]
        n_clusters = int(codes.max()) + 1
        meat = np.zeros((k, k))
        for g in range(n_clusters):
            rows = codes == g
            xg_u = X[rows].T @ resid[rows]
            meat += np.outer(xg_u, xg_u)
        # Standard finite-sample correction (Cameron/Miller); with one
        # cluster it degenerates, so guard it.
        correction = (n_clusters / max(n_clusters - 1, 1)) * ((n - 1) / dof)
        vcov = correction * (xtx_inv @ meat @ xtx_inv)

    se = np.sqrt(np.clip(np.diag(vcov), 0.0, None))
    ss_tot = float(((y - y.mean()) ** 2).sum()) if add_const else float(y @ y)
    r_squared = 1 - float(resid @ resid) / ss_tot if ss_tot > 1e-12 else 0.0

    return {
        "beta": beta, "se": se, "n": n, "dof": dof,
        "r_squared": r_squared, "n_clusters": n_clusters,
        "resid": resid,
    }


def tsls(y: np.ndarray, endog: np.ndarray, exog: np.ndarray | None,
         instruments: np.ndarray, cluster: np.ndarray | None = None,
         absorbed: int = 0, add_const: bool = True) -> dict:
    """Two-stage least squares for a single endogenous regressor (the price).

    Also reports the first-stage F on the excluded instruments, because a
    weak instrument produces a confident-looking number that means nothing,
    and that is worth surfacing next to the estimate rather than burying.
    """
    y = np.asarray(y, dtype=float).ravel()
    endog = np.asarray(endog, dtype=float).ravel()
    Z_excl = _as_2d(instruments)
    exog_2d = _as_2d(exog) if exog is not None else np.empty((len(y), 0))

    base = [np.ones(len(y))] if add_const else []
    W = np.column_stack(base + [exog_2d]) if (base or exog_2d.size) else np.empty((len(y), 0))
    Z = np.column_stack([W, Z_excl]) if W.size else Z_excl

    # First stage: price on everything exogenous plus the instruments.
    first = ols(endog, Z, cluster=cluster, absorbed=absorbed, add_const=False)
    endog_hat = Z @ first["beta"]

    n_excl = Z_excl.shape[1]
    restricted = ols(endog, W, cluster=cluster, absorbed=absorbed, add_const=False) if W.size else None
    if restricted is not None:
        rss_r = float(restricted["resid"] @ restricted["resid"])
        rss_u = float(first["resid"] @ first["resid"])
        dof_u = max(len(y) - Z.shape[1] - absorbed, 1)
        first_stage_f = ((rss_r - rss_u) / n_excl) / (rss_u / dof_u) if rss_u > 1e-12 else float("inf")
    else:
        first_stage_f = float("nan")

    second = ols(y, np.column_stack([endog_hat, exog_2d]) if exog_2d.size else endog_hat,
                 cluster=cluster, absorbed=absorbed, add_const=add_const)

    # The second stage's residuals use fitted price; the honest ones use
    # actual price, and the variance has to be rebuilt from those.
    X_actual = np.column_stack(
        ([np.ones(len(y))] if add_const else []) + [endog.reshape(-1, 1)] +
        ([exog_2d] if exog_2d.size else [])
    )
    X_fitted = np.column_stack(
        ([np.ones(len(y))] if add_const else []) + [endog_hat.reshape(-1, 1)] +
        ([exog_2d] if exog_2d.size else [])
    )
    beta = second["beta"]
    resid = y - X_actual @ beta
    k = X_fitted.shape[1]
    dof = max(len(y) - k - absorbed, 1)
    xtx_inv = np.linalg.pinv(X_fitted.T @ X_fitted)

    if cluster is None:
        vcov = (float(resid @ resid) / dof) * xtx_inv
        n_clusters = None
    else:
        codes = np.unique(np.asarray(cluster), return_inverse=True)[1]
        n_clusters = int(codes.max()) + 1
        meat = np.zeros((k, k))
        for g in range(n_clusters):
            rows = codes == g
            xg_u = X_fitted[rows].T @ resid[rows]
            meat += np.outer(xg_u, xg_u)
        correction = (n_clusters / max(n_clusters - 1, 1)) * ((len(y) - 1) / dof)
        vcov = correction * (xtx_inv @ meat @ xtx_inv)

    se = np.sqrt(np.clip(np.diag(vcov), 0.0, None))
    return {
        "beta": beta, "se": se, "n": len(y), "dof": dof,
        "first_stage_f": float(first_stage_f), "n_clusters": n_clusters,
        "r_squared": float("nan"),  # not meaningful for 2SLS; deliberately not reported
    }


def conditional_logit(X: np.ndarray, chosen: np.ndarray,
                      max_iter: int = 60, tol: float = 1e-9) -> dict:
    """McFadden conditional logit by Newton-Raphson.

    X is (observations, alternatives, regressors); `chosen` is the index of
    the picked alternative per observation. The log-likelihood is globally
    concave, so Newton converges in a few iterations from zero and there is
    no need for a general-purpose optimiser (or a scipy dependency).
    """
    X = np.asarray(X, dtype=float)
    chosen = np.asarray(chosen, dtype=int).ravel()
    n_obs, n_alt, k = X.shape
    beta = np.zeros(k)
    rows = np.arange(n_obs)

    for _ in range(max_iter):
        utility = X @ beta                                  # (n_obs, n_alt)
        utility -= utility.max(axis=1, keepdims=True)       # softmax, stably
        exp_u = np.exp(utility)
        probs = exp_u / exp_u.sum(axis=1, keepdims=True)

        grad = X[rows, chosen, :].sum(axis=0) - np.einsum("ij,ijk->k", probs, X)
        mean_x = np.einsum("ij,ijk->ik", probs, X)          # (n_obs, k)
        hess = -(np.einsum("ij,ijk,ijl->kl", probs, X, X)
                 - np.einsum("ik,il->kl", mean_x, mean_x))

        step = np.linalg.solve(hess, grad)
        beta = beta - step
        if float(np.abs(step).max()) < tol:
            break

    utility = X @ beta
    utility -= utility.max(axis=1, keepdims=True)
    exp_u = np.exp(utility)
    probs = exp_u / exp_u.sum(axis=1, keepdims=True)
    log_lik = float(np.log(np.clip(probs[rows, chosen], 1e-300, None)).sum())
    log_lik_null = float(n_obs * np.log(1.0 / n_alt))

    vcov = np.linalg.pinv(-hess)
    se = np.sqrt(np.clip(np.diag(vcov), 0.0, None))
    return {
        "beta": beta, "se": se, "n": n_obs, "n_alternatives": n_alt,
        "log_lik": log_lik,
        "pseudo_r_squared": 1 - log_lik / log_lik_null if log_lik_null else 0.0,
        "shares": probs.mean(axis=0),
    }


def logit_own_price_elasticity(beta_price: float, se_price: float,
                               prices: np.ndarray, shares: np.ndarray) -> tuple[float, float]:
    """Turn a logit price coefficient into an own-price elasticity.

    For a logit, the own-price elasticity of alternative j is
    beta_price * p_j * (1 - s_j). That is per-alternative; what gets reported
    is the share-weighted average across the brands on the shelf, which is
    the number a category manager would recognise as "how price-sensitive is
    this category's brand demand". The standard error scales linearly with
    beta, since everything else is held at sample means.
    """
    prices = np.asarray(prices, dtype=float)
    shares = np.asarray(shares, dtype=float)
    per_alt = prices * (1 - shares)
    weighted = float((shares * per_alt).sum() / shares.sum())
    return beta_price * weighted, abs(se_price * weighted)


def summarize(beta: float, se: float, n: int, **extra) -> dict:
    """The common shape every benchmark reports, mirroring /elasticity."""
    out = {
        "elasticity": round(float(beta), 3),
        "std_error": round(float(se), 3),
        "ci_low": round(float(beta - Z95 * se), 3),
        "ci_high": round(float(beta + Z95 * se), 3),
        "n_observations": int(n),
        "pct_quantity_change_for_10pct_price_increase": round(((1.10 ** float(beta)) - 1) * 100, 1),
    }
    out.update(extra)
    return out
