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
