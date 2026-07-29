import { defineConfig } from 'astro/config';
import { remarkEncarts } from './src/lib/remark-encarts.mjs';

// Site statique : aucun adaptateur, aucune fonction serveur, aucun runtime.
// `astro build` produit du HTML dans dist/ — c'est tout ce que Vercel sert.
export default defineConfig({
  markdown: {
    remarkPlugins: [remarkEncarts],
    // Pas de coloration syntaxique : le seul bloc de code du site est le
    // modèle de compte-rendu, qui doit rester du texte brut lisible.
    syntaxHighlight: false,
  },
});
