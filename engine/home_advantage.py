"""Host-nation home advantage for WC 2026 (United States, Mexico, Canada).

Research basis: home advantage in international football is worth roughly
+60-100 Elo points (~+0.3-0.4 goals); World Cup hosts win ~62% of matches versus
a 50% neutral baseline (Hvattum & Arntzen 2010; Pollard; bivariate-Poisson home
advantage studies). We apply a deliberately conservative +65 Elo to a host
playing in its own country.

The final draw puts the three hosts in separate groups, so a host is never both
the home and away side in group play. When a host is listed as the *away* team
(its matchday-3 game), the advantage is returned as a negative `home_adv`, which
the model applies in favour of the away side via `(rating_home + home_adv)`.
"""
from __future__ import annotations

HOST_NATIONS = ("United States", "Mexico", "Canada")
HOST_HOME_ADV = 65.0  # Elo points; conservative low end of the 60-100 range


def is_host(team: str) -> bool:
    return team in HOST_NATIONS


def home_adv_for(home: str, away: str) -> float:
    """Signed home advantage (Elo points) applied to the home (first) team.

    +HOST_HOME_ADV when the home team is a host (and the away team is not),
    -HOST_HOME_ADV when the away team is the host (and the home team is not),
    else 0.0 (neutral venue — the default for every non-host group game).
    """
    home_is_host = is_host(home)
    away_is_host = is_host(away)
    if home_is_host and not away_is_host:
        return HOST_HOME_ADV
    if away_is_host and not home_is_host:
        return -HOST_HOME_ADV
    return 0.0


def host_venue_label(home: str, away: str) -> str | None:
    """Human-readable venue label for a host game, or None for a neutral one."""
    adv = home_adv_for(home, away)
    if adv > 0:
        return f"{home} (host)"
    if adv < 0:
        return f"{away} (host)"
    return None
