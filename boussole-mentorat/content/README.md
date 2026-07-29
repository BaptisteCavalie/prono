# Modifier le contenu de la Boussole Mentorat

Ce dossier contient **tout le contenu du site**. Tout ce qui est écrit ici
s'affiche sur les pages. Rien d'autre n'a besoin d'être touché.

Vous n'avez pas besoin de savoir programmer, ni d'installer quoi que ce soit.
Ces fichiers s'ouvrent dans n'importe quel éditeur de texte (Notepad, TextEdit,
Visual Studio Code) et se modifient directement sur GitHub depuis un navigateur.

---

## Ce qu'il y a dans ce dossier

```
content/
├── README.md              ← ce guide
├── formats/               ← une fiche par format d'entretien
│   ├── vision-mentorat.md
│   ├── trajectoire-exaltee.md
│   ├── bilan-de-competences.md
│   ├── expertise-en-action.md
│   ├── accelerateur-mission.md
│   └── format-libre.md
└── pages/
    ├── accueil.md         ← titre et texte de la page d'accueil
    └── dispositif.md      ← la page « Le dispositif »
```

Le **nom du fichier** détermine son adresse sur le site. `bilan-de-competences.md`
donne `…/formats/bilan-de-competences`. Si vous renommez un fichier, l'ancienne
adresse ne fonctionne plus — évitez de le faire sans raison.

---

## Modifier une fiche existante

1. Ouvrez le fichier du format concerné dans `formats/`.
2. Modifiez le texte.
3. Enregistrez (sur GitHub : « Commit changes »).

Le site se met à jour automatiquement en une à deux minutes.

C'est tout. Il n'y a pas d'autre étape, et aucun fichier de code à toucher.

---

## Comment un fichier est construit

Chaque fiche a deux parties.

### 1. L'en-tête, entre deux lignes de trois tirets

```yaml
---
titre: Bilan de compétences
ordre: 3
cadence: Obligatoire, puis à la demande
declenchement: Obligatoire à 8 mois, puis à la demande (recommandé chaque année)
duree: 1h30
prime: 100 €
produit: Une grille de compétences décryptée avec le mentoré, et un plan d'action sur 3 mois.
---
```

Ces sept champs sont **tous obligatoires**. Ils alimentent l'en-tête de la fiche
et sa ligne sur la page d'accueil.

| Champ | À quoi il sert | Remarque |
|---|---|---|
| `titre` | Le nom du format, affiché partout | |
| `ordre` | Position sur la page d'accueil | Un nombre. 1 s'affiche en premier. |
| `cadence` | Étiquette courte « quand ça se déclenche » | S'il commence par le mot **Obligatoire**, l'étiquette s'affiche en plein ; sinon en contour. |
| `declenchement` | La phrase complète du déclenchement | Avec les échéances. |
| `duree` | La durée de l'entretien | Texte libre : `1h30`, `~1h`, `Programme ≤ 3 mois`. |
| `prime` | Le montant | Texte libre, avec le symbole €. |
| `produit` | Une phrase : ce que l'entretien produit | S'affiche sur l'accueil. C'est ce qui aide un mentor à choisir : soyez concret. |

**Attention aux deux-points.** Si une valeur contient `:`, encadrez-la de
guillemets droits :

```yaml
produit: "Un plan d'action : trois axes maximum."
```

### 2. Le corps, après l'en-tête

Le texte de la fiche, découpé en sections. Chaque section commence par deux
dièses :

```markdown
## Avant l'entretien
```

---

## Les sections d'une fiche

Les six fiches suivent **le même ordre**. Conservez-le : c'est ce qui permet à un
mentor de retrouver la même information à la même place d'une fiche à l'autre.

1. `## À quoi ça sert`
2. `## À quoi ça ne sert pas`
3. `## Avant l'entretien`
4. `## Pendant l'entretien`
5. `## Après l'entretien`
6. `## Modèle de compte-rendu`
7. `## Ressources et renvois`

Deux fiches s'écartent un peu de ces intitulés parce que leur objet l'exige
(l'Accélérateur Mission parle de « programme » et non d'« entretien »). C'est
acceptable ; l'ordre, lui, reste le même.

---

## Écrire du texte : l'essentiel

| Pour obtenir | Écrivez |
|---|---|
| Un **titre de section** | `## Mon titre` |
| Un **sous-titre** | `### Mon sous-titre` |
| Du **gras** | `**mon texte**` |
| Une **liste à puces** | Une ligne par point, commençant par `- ` |
| Une **liste numérotée** | `1. `, `2. `, `3. ` |
| Un **lien** | `[Le Hub](https://adresse-du-hub)` |
| Une **question à poser à l'oral** | `*« Ma question ? »*` (entre astérisques) |

Une ligne vide sépare deux paragraphes. Un simple retour à la ligne, non : le
texte reste dans le même paragraphe.

### Ajouter un lien

Beaucoup d'intitulés du site (MentorApp, Le Hub, eXalt Academy) sont
volontairement **sans lien**, parce que leur adresse n'était pas connue à la
création du site. Quand vous connaissez une adresse, remplacez l'intitulé :

```markdown
Avant :  - **MentorApp** — affectation, statut, saisie du compte-rendu.
Après :  - [**MentorApp**](https://adresse-de-la-mentorapp) — affectation, statut, saisie du compte-rendu.
```

N'inventez jamais une adresse. Un intitulé sans lien est préférable à un lien
mort.

---

## Les trois niveaux de fiabilité

C'est le point le plus important de ce site. Le contenu affiché n'a pas partout
le même statut, et **le site le montre** — pour qu'un mentor sache toujours ce
qui est éprouvé et ce qui ne l'est pas.

### Niveau 1 — contenu validé

Du texte normal. Il vient de la documentation du dispositif. Rien à signaler.

### Niveau 2 — proposition à valider

Du contenu utilisable, mais **rédigé hors de la documentation interne** :
formulations de questions, répartitions de temps, modèles de compte-rendu. Il
s'affiche dans un encart avec une barre grise et la mention « Proposition à
valider ».

Pour en écrire un, commencez une citation par `> **[À VALIDER]**` :

```markdown
> **[À VALIDER]** — Formulations proposées, hors documentation interne.
>
> - *« Ma première question ? »*
> - *« Ma deuxième question ? »*
```

**Quand une proposition est confirmée par le responsable mentorat**, faites-la
passer au niveau 1 : retirez la citation, et sortez le texte de l'encart en
supprimant les `> ` en début de ligne.

### Niveau 3 — section à compléter

Une information **qui n'est pas connue**. Elle s'affiche dans un encart encadré
en pointillés bleus, avec la mention « Section non validée », et elle est
comptée en haut de la fiche et sur la page d'accueil.

Pour en écrire une, commencez une citation par `> **[À COMPLÉTER]**`, et
terminez par une ligne indiquant qui solliciter :

```markdown
> **[À COMPLÉTER]** — Délai attendu entre l'entretien et la rédaction du CR.
>
> Source à solliciter : responsable mentorat.
```

La ligne `Source à solliciter :` doit être **séparée par une ligne `>` vide** :
elle s'affiche alors détachée, en bas de l'encart.

**Quand vous obtenez l'information**, supprimez tout l'encart et écrivez le
contenu réel à sa place. Les compteurs se mettent à jour tout seuls.

> **Ne comblez jamais un trou par une supposition.** Un référentiel avec des
> trous assumés est plus sûr qu'un référentiel qui a l'air complet. C'est le
> choix de fond de cet outil : un mentor doit pouvoir faire confiance à ce qui
> n'est pas marqué.

---

## Le modèle de compte-rendu et son bouton « Copier »

Le modèle de CR est le seul bloc du site avec lequel on interagit. Il s'écrit
entre deux lignes de trois accents graves suivies de `cr` :

````markdown
```cr
BILAN DE COMPÉTENCES — [Prénom du mentoré]
Date de l'entretien : [JJ/MM/AAAA]

CONTEXTE
[2 à 3 lignes]
```
````

Le mot `cr` après les trois accents graves est **indispensable** : c'est lui qui
déclenche l'affichage du cadre et du bouton « Copier le modèle de CR ». Sans
lui, le texte s'affiche comme un bloc inerte.

À l'intérieur, écrivez du **texte brut**. Les retours à la ligne, les lignes
vides et les espaces sont conservés tels quels — c'est exactement ce que le
mentor collera dans la MentorApp. N'utilisez ni `**gras**` ni `## titres` : ils
s'afficheraient littéralement.

Les crochets `[…]` signalent au mentor ce qu'il doit remplacer.

---

## Ajouter un nouveau format

1. Créez un fichier dans `formats/`. Nommez-le en minuscules, sans accent et
   sans espace, avec des tirets : `mon-nouveau-format.md`.
2. Copiez l'en-tête d'une fiche existante et adaptez les sept champs. Donnez un
   `ordre` qui le place où vous voulez sur l'accueil — au besoin, renumérotez les
   autres fiches.
3. Reprenez les sept sections dans l'ordre.
4. Pour toute section dont vous n'avez pas la matière, écrivez un bloc
   `[À COMPLÉTER]` plutôt que de deviner.

Le format apparaît sur la page d'accueil dès l'enregistrement. Il n'y a aucune
liste à mettre à jour ailleurs.

## Supprimer un format

Supprimez le fichier. Sa ligne disparaît de l'accueil.

---

## Ce qu'il ne faut pas casser

- **Les trois tirets `---`** qui ouvrent et ferment l'en-tête. Sans eux, la page
  ne se construit plus.
- **Les sept champs d'en-tête.** S'il en manque un, la mise en ligne échoue avec
  un message qui nomme le fichier et le champ manquant. Ce n'est pas grave :
  ajoutez le champ et enregistrez à nouveau.
- **Le mot `cr`** après les trois accents graves du modèle de compte-rendu.
- **La ligne `>` vide** avant `Source à solliciter :`.
- **Les noms de fichiers**, qui servent d'adresses de pages.

Si une modification empêche le site de se construire, **la version précédente
reste en ligne** : le site public n'affiche jamais une page cassée. Corrigez et
enregistrez à nouveau.

---

## Ce que ce site ne fait pas, et ne doit pas faire

Ce référentiel ne contient que du **contenu méthodologique générique**.

N'y écrivez jamais :

- le nom d'un mentoré ou d'un mentor identifiable ;
- le contenu réel d'un compte-rendu d'entretien ;
- une note, une évaluation ou une appréciation concernant une personne ;
- un extrait de grille de compétences remplie.

Les comptes-rendus réels se saisissent dans la **MentorApp**, jamais ici. Le
site est public ou accessible par lien : tout ce qui est écrit dans ce dossier
est lisible par quiconque a l'adresse.
