"""Auto-evaluation of model solidity from completed match results."""
from __future__ import annotations

import copy
import math
from typing import Dict, Iterable, Tuple

from engine import model

K_FACTOR = 24.0


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_key(match: Dict) -> Tuple:
    date_value = match.get("date")
    date_key = str(date_value) if date_value else "9999-99-99"
    return (date_key, match.get("matchday", 99), match.get("id", ""))


def _goal_mult(goal_diff: int, rating_diff: float) -> float:
    return math.log(abs(goal_diff) + 1.0) * (2.2 / (abs(rating_diff) * 0.001 + 2.2))


def _outcome_probs(out: Dict) -> Dict[str, float]:
    return {
        "home": float(out.get("p_home", 0.0)),
        "draw": float(out.get("p_draw", 0.0)),
        "away": float(out.get("p_away", 0.0)),
    }


def _actual_outcome(gh: int, ga: int) -> str:
    if gh > ga:
        return "home"
    if gh < ga:
        return "away"
    return "draw"


def _rps_1x2(probs: Dict[str, float], actual: str) -> float:
    """Ranked Probability Score for a single 1X2 forecast.

    Ordinal metric (home > draw > away) used as the field standard in the
    2017/2023 Soccer Prediction Challenges. Unlike Brier/log-loss it penalises a
    wrong-side miss (predicting away when home wins) more than an adjacent miss
    (predicting a draw). Lower is better; 0 is a perfect forecast.
    """
    order = ("home", "draw", "away")
    cum_p = 0.0
    cum_e = 0.0
    total = 0.0
    for cat in order[:-1]:  # r-1 cumulative steps for r=3 categories
        cum_p += probs.get(cat, 0.0)
        cum_e += 1.0 if cat == actual else 0.0
        total += (cum_p - cum_e) ** 2
    return total / (len(order) - 1)


def assess_model_solidity(fixtures: Iterable[Dict], ratings: Dict, min_sample: int = 8) -> Dict:
    ratings_work = copy.deepcopy(ratings or {})
    teams = ratings_work.get("teams", {})

    n = 0
    exact_hits = 0
    result_hits = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    rps_sum = 0.0
    pick_conf_sum = 0.0
    buckets = {i: {"count": 0, "hits": 0, "conf_sum": 0.0} for i in range(10)}

    for m in sorted(fixtures, key=_sort_key):
        home = m.get("home")
        away = m.get("away")
        if home not in teams or away not in teams:
            continue

        gh = _as_int(m.get("actual_home"))
        ga = _as_int(m.get("actual_away"))
        if gh is None or ga is None:
            continue

        rh = float(teams[home].get("rating", 0.0))
        ra = float(teams[away].get("rating", 0.0))
        home_adv = float(m.get("home_adv", 0.0) or 0.0)

        out = model.analyse(rh, ra, home_adv=home_adv,
                            ad_home=model.ad_from_row(teams[home]),
                            ad_away=model.ad_from_row(teams[away]))
        probs = _outcome_probs(out)
        pick = max(probs.items(), key=lambda kv: kv[1])[0]
        actual = _actual_outcome(gh, ga)

        y = {
            "home": 1.0 if actual == "home" else 0.0,
            "draw": 1.0 if actual == "draw" else 0.0,
            "away": 1.0 if actual == "away" else 0.0,
        }
        brier_sum += (
            (probs["home"] - y["home"]) ** 2
            + (probs["draw"] - y["draw"]) ** 2
            + (probs["away"] - y["away"]) ** 2
        )
        p_actual = max(1e-9, probs[actual])
        logloss_sum += -math.log(p_actual)
        rps_sum += _rps_1x2(probs, actual)
        pick_conf_sum += probs[pick]

        (si, sj), _ = out["top_scores"][0]
        if si == gh and sj == ga:
            exact_hits += 1
        if pick == actual:
            result_hits += 1
        n += 1
        b_idx = min(9, max(0, int(probs[pick] * 10)))
        buckets[b_idx]["count"] += 1
        buckets[b_idx]["hits"] += 1 if pick == actual else 0
        buckets[b_idx]["conf_sum"] += probs[pick]

        expected_home = model.win_expectancy((rh + home_adv) - ra)
        expected_away = 1.0 - expected_home
        if gh > ga:
            actual_home, actual_away = 1.0, 0.0
        elif gh < ga:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        delta = K_FACTOR * _goal_mult(gh - ga, (rh + home_adv) - ra)
        teams[home]["rating"] = round(rh + delta * (actual_home - expected_home), 2)
        teams[away]["rating"] = round(ra + delta * (actual_away - expected_away), 2)

    if n == 0:
        return {
            "matches": 0,
            "score": None,
            "level": "insufficient",
            "result_accuracy": None,
            "exact_score_hit": None,
            "brier_1x2": None,
            "logloss_1x2": None,
            "rps_1x2": None,
            "avg_pick_conf": None,
            "calibration_gap": None,
            "confidence_buckets": [],
            "alerts": ["Aucun match termine: solidite non evaluable pour l'instant."],
        }

    result_accuracy = result_hits / n
    exact_score_hit = exact_hits / n
    brier = brier_sum / n
    logloss = logloss_sum / n
    rps = rps_sum / n
    avg_pick_conf = pick_conf_sum / n
    calibration_gap = avg_pick_conf - result_accuracy

    confidence_buckets = []
    for idx in range(10):
        row = buckets[idx]
        count = row["count"]
        if count == 0:
            continue
        low = idx * 10
        high = low + 9
        hit_rate = row["hits"] / count
        avg_conf = row["conf_sum"] / count
        confidence_buckets.append({
            "range": f"{low}-{high}%",
            "count": count,
            "hit_rate": hit_rate,
            "avg_conf": avg_conf,
            "gap": avg_conf - hit_rate,
        })

    brier_norm = max(0.0, min(1.0, 1.0 - (brier / 1.2)))
    logloss_norm = max(0.0, min(1.0, 1.0 - (logloss / 1.4)))
    score = int(round(
        (50.0 * result_accuracy)
        + (20.0 * brier_norm)
        + (20.0 * logloss_norm)
        + (10.0 * exact_score_hit)
    ))
    score = max(0, min(100, score))

    if score >= 75:
        level = "solid"
    elif score >= 55:
        level = "mixed"
    else:
        level = "fragile"

    alerts = []
    if n < min_sample:
        alerts.append(f"Echantillon faible ({n} matchs): score encore instable.")
    if result_accuracy < 0.45:
        alerts.append("Precision 1N2 faible: recalibrage conseille.")
    if calibration_gap > 0.12:
        alerts.append("Confiance trop optimiste vs resultats reels.")
    if calibration_gap < -0.12:
        alerts.append("Confiance trop prudente: le modele sous-estime ses bons picks.")

    return {
        "matches": n,
        "score": score,
        "level": level,
        "result_accuracy": result_accuracy,
        "exact_score_hit": exact_score_hit,
        "brier_1x2": brier,
        "logloss_1x2": logloss,
        "rps_1x2": rps,
        "avg_pick_conf": avg_pick_conf,
        "calibration_gap": calibration_gap,
        "confidence_buckets": confidence_buckets,
        "alerts": alerts,
    }
