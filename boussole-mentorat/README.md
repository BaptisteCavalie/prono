# Boussole Mentorat

Référentiel consultable des 6 formats d'entretien du Service Mentorat eXalt.
Pour chaque format : ce qu'il produit, comment le dérouler, et un modèle de
compte-rendu à copier.

Site statique. Pas de compte, pas de base de données, pas de backend, aucune
donnée personnelle.

> **Statut.** Initiative personnelle, à présenter au responsable mentorat. Ce
> n'est pas un outil officiel eXalt, et il ne remplace aucune fonction de la
> MentorApp.

---

## Installation et lancement

Nécessite Node.js 18 ou plus.

```bash
npm install
npm run dev
```

Le site tourne sur <http://localhost:4321>.

Pour vérifier ce qui sera publié :

```bash
npm run build     # génère dist/
npm run preview   # sert dist/ localement
```

---

## Modifier le contenu

**Tout le contenu est dans `content/`, en Markdown.** Un fichier par format.
Aucune phrase de contenu métier n'est écrite dans le code.

Le guide d'édition, rédigé pour quelqu'un qui ne programme pas, est dans
[`content/README.md`](content/README.md). Il couvre : modifier une fiche,
ajouter un format, les trois niveaux de fiabilité, et ce qu'il ne faut pas
casser.

En pratique, le responsable mentorat édite un fichier `.md` directement depuis
l'interface web de GitHub et enregistre. Vercel reconstruit et publie
automatiquement. Aucune installation, aucune commande.

---

## Arborescence

```
boussole-mentorat/
├── content/                    ← LE CONTENU (éditable sans développeur)
│   ├── README.md               ← guide d'édition
│   ├── formats/*.md            ← une fiche par format
│   └── pages/*.md              ← accueil et « Le dispositif »
├── public/fonts/               ← Poppins (self-hébergée)
├── src/
│   ├── content.config.mjs      ← schéma du front-matter (validé au build)
│   ├── layouts/Base.astro      ← châssis + bouton « Copier »
│   ├── lib/
│   │   ├── remark-encarts.mjs  ← encarts de fiabilité, bloc CR
│   │   └── marqueurs.mjs       ← comptage des sections à compléter
│   ├── pages/
│   │   ├── index.astro         ← accueil : les 6 formats
│   │   ├── dispositif.astro    ← les règles transverses
│   │   └── formats/[id].astro  ← une page par fiche
│   └── styles/global.css       ← feuille unique, charte eXalt
├── astro.config.mjs
└── vercel.json
```

---

## Déploiement

Le projet est un site statique : `npm run build` produit `dist/`, qui se sert
tel quel.

**Sur Vercel** — importer le dépôt, aucune configuration à saisir. Vercel
détecte Astro et applique `npm run build` → `dist/`. Si le projet vit dans un
sous-dossier d'un dépôt plus large, renseigner **Root Directory** =
`boussole-mentorat`.

Chaque enregistrement sur la branche principale republie le site.

---

## Décisions

Chaque choix, et sa raison en une ligne.

| Décision | Raison |
|---|---|
| **Astro en sortie statique** | Markdown natif, aucun serveur, aucun runtime — le HTML se sert tel quel. |
| **Contenu dans `content/`, hors de `src/`** | Rend évident qu'on édite le contenu sans entrer dans le code. |
| **Front-matter validé au build (content collections)** | Une erreur d'édition produit un message nommant le fichier et le champ, au lieu d'une page cassée en silence. |
| **Un fichier Markdown par format** | Modifier une trame = éditer un seul fichier ; ajouter un format = ajouter un fichier, sans liste à tenir ailleurs. |
| **Sept champs de front-matter, tous plats** | Un schéma qu'on comprend sans documentation ; pas de structure imbriquée à respecter. |
| **Trois niveaux de fiabilité affichés** | Un mentor doit distinguer d'un coup d'œil l'éprouvé, la proposition et le trou. Un référentiel qui a l'air complet est plus dangereux qu'un référentiel troué. |
| **Marqueurs `[À COMPLÉTER]` / `[À VALIDER]` en Markdown standard** | S'écrivent sans connaître le code ; la convention est du texte, pas une balise. |
| **Compteurs de trous calculés à la construction** | Le nombre affiché ne peut pas se désynchroniser du contenu réel. |
| **Bloc de code ```cr → widget de copie** | Le modèle de CR reste du texte brut éditable, et le bouton apparaît tout seul. |
| **~15 lignes de JavaScript, aucune dépendance client** | Une seule interaction sur le site ; un framework serait disproportionné. |
| **Repli sur sélection du texte si le presse-papier échoue** | En HTTP ou permission refusée, la copie reste à un raccourci près. |
| **Poppins self-hébergée (4 graisses, latin, 31 Ko)** | Aucune requête vers un tiers : plus rapide, et pas de dépendance externe pour un outil interne. |
| **Charte eXalt Group** | Reprise de la charte trouvée dans l'environnement (Poppins, Bleu eXalt `#5853FF`, texte `#08006C`). Ombres et dégradés du kit slides écartés : la direction visuelle voulue est institutionnelle, pas commerciale. |
| **Un seul accent, le Bleu eXalt** | Réservé aux actions et aux encarts de fiabilité, pour que le signal reste un signal. |
| **Feuille de style unique, sans utilitaires** | Le site fait trois gabarits ; un système de classes utilitaires coûterait plus qu'il ne rend. |
| **`noindex, nofollow`** | Contenu interne : accessible par lien, pas référencé publiquement. |
| **Aucun analytics, aucun cookie, aucun formulaire** | Rien à collecter, donc rien à protéger. |

### Ce qui a été délibérément écarté

Recherche, filtres, page « à propos », authentification, base de données,
génération de compte-rendu, statistiques d'usage, variantes de contenu par
niveau de mentor. Le site fait trois pages et un bouton.
