"""Paired tests use aligned question IDs supplied by the caller."""
import numpy as np
from scipy.stats import binomtest, rankdata, wilcoxon


def paired(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or not len(a) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Paired finite, nonempty arrays of equal length required')
    return a, b


def mcnemar(a, b):
    a, b = paired(a, b)
    if not np.isin(a, [0, 1]).all() or not np.isin(b, [0, 1]).all():
        raise ValueError('Binary correctness required')
    wins, losses = int(((a == 1) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    return dict(a_only=wins, b_only=losses,
                p_value=float(binomtest(wins, wins + losses, .5).pvalue) if wins + losses else 1.0)


def continuous(a, b, resamples=2000, seed=42, confidence=.95):
    a, b = paired(a, b)
    if resamples < 1 or not 0 < confidence < 1:
        raise ValueError('Invalid bootstrap settings')
    d = a - b
    nonzero = d[d != 0]
    ranks = rankdata(abs(nonzero))
    effect = float((ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum()) / ranks.sum()) if len(nonzero) else 0.0
    p = float(wilcoxon(d, zero_method='wilcox', alternative='two-sided', method='auto').pvalue) if len(nonzero) else 1.0
    rng = np.random.default_rng(seed)
    boot = [rng.choice(d, size=len(d), replace=True).mean() for _ in range(resamples)]
    alpha = (1 - confidence) / 2
    return dict(mean_difference=float(d.mean()), wilcoxon_p=p, rank_biserial=effect,
                bootstrap_ci=np.quantile(boot, [alpha, 1-alpha]).tolist(), resamples=resamples, seed=seed)


def holm(p_values):
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError('Invalid p-values')
    order = np.argsort(values, kind='stable')
    adjusted = np.empty(len(values))
    floor = 0.0
    for i, j in enumerate(order):
        floor = max(floor, min(1.0, (len(values) - i) * values[j]))
        adjusted[j] = floor
    return adjusted.tolist()
