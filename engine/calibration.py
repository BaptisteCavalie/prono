"""Post-hoc 1X2 calibration: temperature scaling to tame favourite overconfidence.

Why a *second* calibration lever (on top of ``model.RATING_SHRINK``): RATING_SHRINK
damps the rating gap before it drives goals, but the resulting 1X2 vector is still
overconfident at the extreme top. On the WC2026 group stage the model's
reconstructed *as-of* log-loss (1.105) was WORSE than a flat 33/33/33 coin (1.099):
a handful of "locks" priced ~95% (Spain–Cape Verde, Portugal–DR Congo) drew, and the
90-99% confidence bucket only hit ~57-60%. Brier and RPS beat uniform, but the
probabilities themselves were the model's weak point.

Fix: temperature scaling — ``p_i' ∝ p_i**(1/T)``, renormalised. ``T > 1`` softens the
distribution (pulls the extremes toward the centre). It is strictly monotone, so the
most likely outcome — the pick, the 1X2 accuracy, the frozen MPP scoreline — NEVER
changes; only the *confidence* is pulled toward honesty. This is the textbook
recalibration method (Platt/temperature scaling), a single parameter, fit to
minimise log-loss.

T is chosen conservatively. The log-loss-minimising basin is broad and — crucially —
replicates OUT OF SAMPLE across two tournaments, both bottoming out around T≈2.0-2.3:

    WC2026 (44 matchs, reconstruction as-of):  1.105 (T=1) -> 1.005 (T=1.5) -> 0.981 (T=2.3)
    WC2022 (48 matchs de poule, hors échant.): 1.139 (T=1) -> 1.064 (T=1.5) -> 1.045 (T=2.3)

We deliberately pick the lower edge, ``T = 1.5``, rather than the raw optimum: it
captures ~80% of the log-loss gain while keeping the model expressive on genuine
mismatches (a 95% blowout becomes ~85%, not ~75%), instead of over-flattening on a
sample with a couple of high-confidence flukes.

Scope — this is a *confidence / EV* layer, not a new model. It feeds the displayed
distribution, the confidence verdict, the value/EV comparison and the solidity
self-assessment. It does NOT touch ``model.analyse``'s raw probabilities or the
Poisson score grid, so the MPP scoreline pick and every frozen prono stay
byte-for-byte identical (no "prono mis à jour" phantom updates).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Temperature for 1X2 recalibration. 1.0 disables it (identity). See the module
# docstring for the two-tournament fit and why the conservative 1.5 is used.
CALIBRATION_T = 1.5


def temper(probs: List[float], temperature: float = CALIBRATION_T) -> List[float]:
    """Temperature-scale a probability vector: ``p_i**(1/T)`` renormalised.

    ``T > 1`` softens (less confident), ``T < 1`` sharpens, ``T == 1`` is the
    identity (bar renormalisation). The transform is monotone, so the argmax is
    preserved. Non-positive entries are held at 0; an all-zero or empty input is
    returned unchanged (defensively renormalised).
    """
    if temperature <= 0:
        raise ValueError(f"temperature must be > 0, got {temperature!r}")
    if temperature == 1.0:
        s = sum(probs)
        return [p / s for p in probs] if s else list(probs)
    powered = [p ** (1.0 / temperature) if p > 0 else 0.0 for p in probs]
    s = sum(powered)
    if not s:
        return list(probs)
    return [p / s for p in powered]


def calibrated_1x2(out: Dict, temperature: float = CALIBRATION_T) -> Tuple[float, float, float]:
    """Temperature-calibrated ``(p_home, p_draw, p_away)`` for a model output."""
    h, d, a = temper(
        [float(out["p_home"]), float(out["p_draw"]), float(out["p_away"])],
        temperature,
    )
    return h, d, a


def calibrated_probs(out: Dict, temperature: float = CALIBRATION_T) -> Dict[str, float]:
    """Same as :func:`calibrated_1x2`, keyed ``{'home', 'draw', 'away'}``."""
    h, d, a = calibrated_1x2(out, temperature)
    return {"home": h, "draw": d, "away": a}
