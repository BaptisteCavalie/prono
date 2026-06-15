"""Helpers shared by the CLI (predict.py / bet.py) and the web UI (ui.py)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class UserFacingError(ValueError):
    """Error whose message is safe and useful to show to an end user."""


def split_match(s: str) -> Optional[Tuple[str, str]]:
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def match_key(match: Dict) -> str:
    return f"{match['home'].strip().lower()}|{match['away'].strip().lower()}"


def find_match_odds(match: Dict, board: Dict[str, List[float]]):
    if not board:
        return None
    return board.get(str(match.get("id", "")).upper()) or board.get(match_key(match))


def parse_date(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


# Les trois verdicts de justesse d'un prono, alignés sur la logique Mon Petit
# Prono : score juste (gros bonus), bon résultat 1N2 (points moindres), erreur
# (0). Ce sont des compteurs descriptifs a posteriori — jamais une note de
# certitude du modèle, dont la sortie reste une distribution calibrée.
PRONO_CATEGORIES = ("exact", "bon", "erreur")


def _outcome(home: int, away: int) -> int:
    """1 = victoire domicile, 0 = nul, -1 = victoire extérieur."""
    return (home > away) - (home < away)


def classify_prono(pred_home, pred_away, act_home, act_away) -> Optional[str]:
    """Compare un prono figé (score) au résultat réel.

    Renvoie ``"exact"`` (score juste), ``"bon"`` (bon résultat 1N2 mais score
    faux), ``"erreur"`` (mauvais résultat), ou ``None`` si une donnée manque
    (match non joué ou prono non figé). Comparer un prono recalculé après le
    résultat n'aurait pas de sens : on n'appelle cette fonction qu'avec le
    score figé d'avant-match.
    """
    if any(v is None for v in (pred_home, pred_away, act_home, act_away)):
        return None
    try:
        ph, pa, ah, aa = int(pred_home), int(pred_away), int(act_home), int(act_away)
    except (TypeError, ValueError):
        return None
    if ph == ah and pa == aa:
        return "exact"
    if _outcome(ph, pa) == _outcome(ah, aa):
        return "bon"
    return "erreur"


def tally_pronos(verdicts) -> Dict[str, int]:
    """Agrège des verdicts (sortie de :func:`classify_prono`) en compteurs.

    Les verdicts ``None`` sont ignorés. Renvoie un dict avec une clé par
    catégorie plus ``total`` (nombre de matchs effectivement comptés).
    """
    counts: Dict[str, int] = {c: 0 for c in PRONO_CATEGORIES}
    for verdict in verdicts:
        if verdict in counts:
            counts[verdict] += 1
    counts["total"] = sum(counts[c] for c in PRONO_CATEGORIES)
    return counts


# Statuts de règlement d'un pari réel (saisis par la couche ask-Claude dans
# data/bets.json, jamais dans l'UI). « en_cours » = pari placé non encore réglé.
BET_STATUSES = ("gagne", "perdu", "rembourse", "en_cours")
SETTLED_STATUSES = ("gagne", "perdu", "rembourse")


def bet_status(bet: Dict) -> str:
    """Statut normalisé d'un pari ; ``en_cours`` par défaut / si inconnu."""
    s = str(bet.get("status") or "en_cours").strip().lower()
    return s if s in BET_STATUSES else "en_cours"


def bet_net(bet: Dict) -> Optional[float]:
    """Gain net d'un pari réglé, du seul point de vue de la mise.

    ``gagne`` → mise × (cote − 1) ; ``perdu`` → −mise ; ``rembourse`` → 0.
    Renvoie ``None`` si le pari est en cours ou si mise/cote sont inexploitables
    (un pari non réglé n'a pas de P&L ; on ne devine pas). Logique argent : pure
    et testée (tests/test_bets.py).
    """
    status = bet_status(bet)
    if status not in SETTLED_STATUSES:
        return None
    try:
        stake = float(bet.get("stake"))
        odds = float(bet.get("odds"))
    except (TypeError, ValueError):
        return None
    if stake < 0 or odds < 1:
        return None
    if status == "gagne":
        return stake * (odds - 1.0)
    if status == "perdu":
        return -stake
    return 0.0  # rembourse


def tally_bets(bets) -> Dict:
    """Bilan cumulé tournoi des paris réglés : compteurs, mise, P&L, ROI.

    Comptage « argent réel » a posteriori, distinct du récap justesse des
    pronos (1N2). Les paris en cours sont comptés à part (``n_pending``),
    jamais dans la mise/P&L réglés ; leur exposition vit dans
    ``staked_pending`` (mise totale en cours) et ``potential_pending`` (gain
    total possible si tout passe = mise × cote, brut). ``roi`` vaut ``None``
    tant qu'aucune mise réglée n'est engagée.
    """
    agg = {"n_settled": 0, "n_won": 0, "n_lost": 0, "n_refunded": 0,
           "n_pending": 0, "staked": 0.0, "net": 0.0, "roi": None,
           "staked_pending": 0.0, "potential_pending": 0.0}
    for b in bets:
        status = bet_status(b)
        if status not in SETTLED_STATUSES:
            agg["n_pending"] += 1
            # Exposition des paris en cours : mise totale engagée + gain total
            # possible si tout passe (mise × cote = « gains potentiels » Winamax,
            # brut). Mêmes garde-fous que bet_net : mise/cote inexploitable ignorée.
            try:
                stake = float(b.get("stake"))
                odds = float(b.get("odds"))
            except (TypeError, ValueError):
                continue
            if stake >= 0 and odds >= 1:
                agg["staked_pending"] += stake
                agg["potential_pending"] += stake * odds
            continue
        net = bet_net(b)
        if net is None:           # réglé mais mise/cote inexploitables : on ignore
            continue              # plutôt que de corrompre la mise totale
        agg["staked"] += float(b.get("stake"))
        agg["net"] += net
        agg["n_settled"] += 1
        if status == "gagne":
            agg["n_won"] += 1
        elif status == "perdu":
            agg["n_lost"] += 1
        else:
            agg["n_refunded"] += 1
    if agg["staked"] > 0:
        agg["roi"] = agg["net"] / agg["staked"]
    return agg


def leg_outcome(home_goals: int, away_goals: int) -> str:
    """1N2 d'un match terminé : ``home`` / ``draw`` / ``away``."""
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def settle_status(bet: Dict, results: Dict[str, Tuple[int, int]]) -> str:
    """Statut réglé d'un pari Winamax d'après les résultats connus.

    ``results`` : ``{MATCH_ID: (buts_dom, buts_ext)}`` pour les seuls matchs
    **terminés**. Logique combiné (et simple = 1 jambe) :

    - **perdu** dès qu'**une** jambe est perdue (même si d'autres sont à jouer) ;
    - **gagne** seulement quand **toutes** les jambes sont jouées ET gagnées ;
    - **en_cours** sinon (au moins une jambe pas encore jouée, aucune perdue).

    Ne statue jamais « remboursé » (annulation / cote void) : ces cas restent
    manuels (cf. maj-resultats). Un pari sans ``legs`` (ancien format) garde son
    statut tel quel — on ne devine pas. Fonction pure, testée (tests/test_bets.py).
    """
    legs = bet.get("legs")
    if not legs:
        return bet_status(bet)
    any_pending = False
    for leg in legs:
        res = results.get(str(leg.get("match", "")).upper())
        if res is None:
            any_pending = True
            continue
        try:
            outcome = leg_outcome(int(res[0]), int(res[1]))
        except (TypeError, ValueError):
            any_pending = True   # malformed score → treat as not yet decided
            continue
        if outcome != leg.get("pick"):
            return "perdu"
    return "en_cours" if any_pending else "gagne"


def load_odds_board(path: Optional[str], root: Optional[Path] = None) -> Dict[str, List[float]]:
    """Parse a {key: [home, draw, away]} decimal-odds JSON file.

    With `root`, the path comes from an untrusted HTTP query parameter: it is
    confined under `root` and every failure raises a UserFacingError that does
    not echo resolved filesystem paths. Without `root` (CLI), any local path
    the user owns is accepted.
    """
    if not path:
        return {}

    if root is not None:
        base = root.resolve()
        resolved = (base / path).resolve()
        if not resolved.is_relative_to(base):
            raise UserFacingError(
                "Fichier de cotes non autorisé : indiquez un fichier JSON du projet (ex. data/odds_md1.json)."
            )
        if not resolved.is_file():
            raise UserFacingError(
                "Fichier de cotes introuvable : vérifiez le chemin (ex. data/odds_md1.json)."
            )
        target = resolved
    else:
        target = Path(path)

    try:
        with open(target, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise UserFacingError("Fichier de cotes illisible : le contenu n'est pas du JSON valide.") from exc

    if not isinstance(raw, dict):
        raise UserFacingError("Fichier de cotes invalide : objet JSON {clé: [domicile, nul, extérieur]} attendu.")

    board: Dict[str, List[float]] = {}
    for key, triple in raw.items():
        if (not isinstance(triple, list) or len(triple) != 3
                or not all(isinstance(x, (int, float)) for x in triple)):
            raise UserFacingError(
                f"Cotes invalides pour {key!r} : format attendu [domicile, nul, extérieur] en cotes décimales."
            )

        if key.lower().startswith("g"):
            board[key.upper()] = [float(x) for x in triple]
            continue

        pair = split_match(key)
        if pair:
            board[f"{pair[0].lower()}|{pair[1].lower()}"] = [float(x) for x in triple]
            continue

        raise UserFacingError(
            f"Clé de cotes invalide {key!r} : utilisez l'id du match (ex. G01) ou 'Équipe A vs Équipe B'."
        )

    return board
