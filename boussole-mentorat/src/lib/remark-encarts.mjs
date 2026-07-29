/**
 * Transforme deux conventions d'écriture Markdown en éléments de page.
 *
 * 1. Une citation qui commence par **[À COMPLÉTER]** ou **[À VALIDER]**
 *    devient un encart signalant le niveau de fiabilité de la section.
 * 2. Un bloc de code ```cr devient le modèle de compte-rendu, avec son
 *    bouton « Copier ».
 *
 * Ces deux conventions sont documentées dans content/README.md. Elles sont
 * volontairement écrites en Markdown standard : un fichier de contenu reste
 * lisible et modifiable sans connaître ce fichier-ci.
 */

const NIVEAUX = [
  {
    marqueur: '[À COMPLÉTER]',
    classe: 'encart encart--trou',
    etiquette: 'Section non validée',
  },
  {
    marqueur: '[À VALIDER]',
    classe: 'encart encart--proposition',
    etiquette: 'Proposition à valider',
  },
];

function texteBrut(node) {
  if (!node) return '';
  if (typeof node.value === 'string') return node.value;
  if (Array.isArray(node.children)) return node.children.map(texteBrut).join('');
  return '';
}

function echapper(valeur) {
  return valeur
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function visiter(node, parent, index, actions) {
  if (!node || typeof node !== 'object') return;

  if (Array.isArray(node.children)) {
    // À l'envers : une action peut remplacer l'enfant courant.
    for (let i = node.children.length - 1; i >= 0; i -= 1) {
      visiter(node.children[i], node, i, actions);
    }
  }

  for (const action of actions) action(node, parent, index);
}

function marquerEncarts(node) {
  if (node.type !== 'blockquote') return;

  const debut = texteBrut(node.children?.[0]).trimStart();
  const niveau = NIVEAUX.find((n) => debut.startsWith(n.marqueur));
  if (!niveau) return;

  node.data = node.data || {};
  node.data.hName = 'aside';
  node.data.hProperties = {
    class: niveau.classe,
    'data-etiquette': niveau.etiquette,
    // Lu comme un aparté par les lecteurs d'écran, pas comme une citation.
    'aria-label': niveau.etiquette,
  };

  retirerMarqueur(node, niveau.marqueur);
  marquerSource(node);
}

/**
 * Le marqueur écrit dans le fichier est retiré du rendu : l'encart affiche
 * déjà son étiquette de fiabilité, le répéter en gras n'ajoute rien.
 */
function retirerMarqueur(blockquote, marqueur) {
  const premier = blockquote.children?.[0];
  if (premier?.type !== 'paragraph' || !Array.isArray(premier.children)) return;

  const [tete, ...reste] = premier.children;
  if (tete?.type !== 'strong') return;
  if (!texteBrut(tete).trim().startsWith(marqueur)) return;

  premier.children = reste;

  // Retire le tiret de liaison qui suivait le marqueur.
  const suivant = premier.children[0];
  if (suivant?.type === 'text') {
    suivant.value = suivant.value.replace(/^\s*[—–-]\s*/, '');
  }

  if (premier.children.length === 0) blockquote.children.shift();
}

/** La ligne « Source à solliciter » est une note de bas d'encart, pas du corps. */
function marquerSource(blockquote) {
  for (const enfant of blockquote.children ?? []) {
    if (enfant.type !== 'paragraph') continue;
    if (!texteBrut(enfant).trimStart().startsWith('Source à solliciter')) continue;
    enfant.data = enfant.data || {};
    enfant.data.hProperties = { class: 'encart__source' };
  }
}

function construireModeleCr(contenu) {
  const brut = echapper(contenu);
  return [
    // Pas de titre ici : le fichier de contenu porte déjà son titre de section
    // juste au-dessus du bloc.
    '<section class="cr" aria-label="Modèle de compte-rendu">',
    '<div class="cr__entete">',
    '<p class="cr__legende">Texte brut, à coller dans la MentorApp</p>',
    '<button type="button" class="cr__bouton" data-copier-cr>',
    '<span data-libelle-copie>Copier le modèle de CR</span>',
    '</button>',
    '</div>',
    `<pre class="cr__texte" data-source-cr>${brut}</pre>`,
    '</section>',
  ].join('');
}

function remplacerModeleCr(node, parent, index) {
  if (node.type !== 'code' || node.lang !== 'cr') return;
  if (!parent || typeof index !== 'number') return;

  parent.children[index] = {
    type: 'html',
    value: construireModeleCr(node.value ?? ''),
  };
}

export function remarkEncarts() {
  return (tree) => {
    visiter(tree, null, null, [marquerEncarts, remplacerModeleCr]);
  };
}
