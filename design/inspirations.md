# Banque d'inspirations — prono (WC 2026)

> Dépôt brut, **distinct du DA curé** (`da.md`, « Références — 3 max »).
> Ici on accumule ; là-bas on tranche. Une inspi ne monte dans `da.md` que
> validée par Baptiste. Chaque entrée porte un **verdict** : `à curer`
> (candidate au DA), `pattern feature` (utile à un écran, pas au parti-pris),
> ou `anti-modèle` (gardée pour savoir ce qu'on refuse).
>
> Captures : les images vivent dans `design/references/<slug>.png` — le
> design-critic les ouvre côte à côte avec le rendu. Les 5 ci-dessous,
> partagées en chat (2026-06-15), sont **déposées** dans `references/`.

---

## ScoreZone — scores live, sidebar par compétition + filtre pays
- **Capture** : `design/references/scorezone-dark-scores.png`
- **Verdict** : `pattern feature` (sidebar/filtre) + `anti-modèle` (le reste)
- **On vole** : la **sidebar listée par compétition** doublée d'un bloc
  **Countries avec drapeaux** — exactement notre geste cardinal (filtre pays
  instantané) ; les **cartes match team-vs-team** scannables en grille
  (crest · crest, score, statut/minute) pour la liste Matchs.
- **On laisse** : le **dark sur TOUT le contenu**, le hero vidéo « FINAL »
  promo, les **compteurs de viewers** (engagement/social) — toute la culture
  qu'on rejette ; chez nous le sombre s'arrête à la nav.

## VELO — cockpit F1, canvas clair « instrument pro »
- **Capture** : `design/references/velo-f1-light-cockpit.png`
- **Verdict** : `à curer` (forte affinité avec le parti-pris dashboard)
- **On vole** : le **canvas papier clair encadré par une sidebar** (notre
  parti-pris exact) ; la **table Standings dense** (drapeau + nom + valeur
  chiffrée alignée) — pile le besoin classement/probas ; les **barres-meters
  horizontales** qui décomposent un facteur en % (écho du Nutri-prono
  décomposé) ; le **statut en pastille discrète** (« Circuit Completed »)
  plutôt qu'un bandeau.
- **On laisse** : l'**accent bleu froid** (on garde le teal chaud) ; l'appareil
  F1 (circuit map, météo) hors-sujet.

## VitalView — santé, right-rail récap + cartes-stat
- **Capture** : `design/references/vitalview-health-rightrail.png`
- **Verdict** : `pattern feature` (récap latéral, hiérarchie du chiffre)
- **On vole** : le **right-rail de récap** (mini-calendrier + stats de la
  période) si un récap latéral aide ; la **hiérarchie chiffre géant + unité**
  lisible d'un coup d'œil ; la **carte-stat avec sparkline intégrée**
  (valeur + tendance dans la même tuile).
- **On laisse** : les **pastels décoratifs** (chez nous A–E code la confiance,
  jamais la déco) ; le ton grand public et les illustrations de fond.

## Tips app (profil « Max Kembli ») — social betting vert
- **Capture** : `design/references/bettingtips-green-social.png`
- **Verdict** : `anti-modèle` (le specimen le plus pur de ce qu'on refuse)
- **On vole** (rare) : la **liste de matchs à onglets de statut**
  (All · Live · Finished · Scheduled) — écho de notre fusion passés/futurs
  masquables ; l'idée d'un **graphe P&L/ROI** latéral (notre page Paris suit
  P&L + ROI).
- **On laisse** : **balance évolutive, « Add Tips », notifications « +Profit »,
  Followers/Following, « Hot Tips »** — toute la mécanique d'incitation,
  d'urgence et de dopamine. On a explicitement écarté la bankroll ; P&L/ROI
  restent neutres, aucune incitation à parier.

## SPORTSTENSOR — prédictions + leaderboard ROI, canvas clair
- **Capture** : `design/references/sportstensor-predictions-roi.png`
- **Verdict** : `à curer` (prolonge FiveThirtyEight, déjà au DA)
- **On vole** : la **prédiction comme objet premier** (Total Predictions,
  Score Per Miner) ; le **leaderboard avec ROI chiffré** aligné (page Paris :
  ROI cumulé tournoi) ; les **chips de filtre instantané** (notre filtre pays) ;
  la **liste d'odds « upcoming » avec sparkline** (tendance de cote) sur un
  **canvas clair data-dense + sidebar par sport**.
- **On laisse** : le **jargon crypto** (miners, HotKey) ; l'esthétique violette
  SaaS ; la cote mise en avant comme incitation.

---

## Lecture d'ensemble
Cinq dashboards sportifs, deux camps nets :
- **Le bon côté** (VELO, SPORTSTENSOR) confirme le parti-pris : **canvas clair
  data-dense + sidebar châssis**, table/leaderboard chiffré, prédiction en
  vedette. À curer vers `da.md` si on remplace une référence.
- **L'anti-modèle** (tips app verte, ScoreZone en dark total) confirme la règle
  cardinale : **le sombre et la promo s'arrêtent à la nav**, jamais sur la
  donnée de pari — gardés ici pour nommer ce qu'on refuse.
Patterns réutilisables transverses : **filtre pays/sport en chips ou liste
sidebar**, **sparkline dans la tuile** (valeur + tendance), **statut en
pastille** plutôt qu'en bandeau.

## Ce que Baptiste retient (2026-06-15)
Réactions sur les 5 dashboards — traces de goût, validées.
- **Écusson/drapeau > nom** : l'identité visuelle de l'équipe prime sur le
  texte. À appliquer à nos **drapeaux** (filtre pays et lignes de match mènent
  au drapeau, nom en secondaire). → porté dans `da.md`.
- **Architecture des cards de match** : la hiérarchie d'info dans une carte
  match (équipes · statut/minute · score · méta) — référence de composition
  pour la liste Matchs. → pattern feature.
- **Fonds blancs « dashboard » + colonnes** : panneaux juxtaposés sur canvas
  clair — confirme le parti-pris. → déjà au DA, renforcé (layout colonnes).
- **Chiffres-clés très mis en avant** : hiérarchie d'échelle forte sur les
  nombres (proba, ROI, P&L). → porté dans `da.md` (Typographie).
- **Gold / silver / copper light pour les Paris** : **ADOPTÉ** (Baptiste
  2026-06-15) — « c'est un outil perso, je m'en fiche de l'incitation ».
  Devient le **médaillon podium des 3 plus gros gains** du tournoi (or 1er,
  argent 2e, cuivre 3e), pâle et mat ; le P&L reste coloré **vert gain / rouge
  perte**. → porté dans `da.md` (Couleur · Paris).
