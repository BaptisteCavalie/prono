/**
 * Compte les marqueurs de fiabilité présents dans un fichier de contenu.
 * Sert à afficher, sur l'accueil et en tête de fiche, ce qui reste à valider —
 * avant que le mentor ait commencé à lire.
 */

const MARQUEUR_TROU = '[À COMPLÉTER]';
const MARQUEUR_PROPOSITION = '[À VALIDER]';

function compter(texte, marqueur) {
  return texte.split(marqueur).length - 1;
}

export function compterMarqueurs(corps = '') {
  return {
    trous: compter(corps, MARQUEUR_TROU),
    propositions: compter(corps, MARQUEUR_PROPOSITION),
  };
}
