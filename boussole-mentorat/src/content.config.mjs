import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

/**
 * Le contenu vit dans content/, hors de src/, pour qu'il reste évident qu'on
 * peut l'éditer sans toucher au code. Le schéma ci-dessous est volontairement
 * plat : sept champs, tous lisibles. Si un champ manque ou se trompe de type,
 * `npm run build` s'arrête avec un message nommant le fichier et le champ —
 * c'est le garde-fou de l'édition sans développeur.
 */

const formats = defineCollection({
  loader: glob({ pattern: '*.md', base: './content/formats' }),
  schema: z.object({
    // Nom du format, tel qu'il s'affiche partout.
    titre: z.string(),
    // Ordre d'affichage sur l'accueil (1 = en premier).
    ordre: z.number(),
    // Étiquette courte : « Obligatoire » ou « À la demande ».
    cadence: z.string(),
    // Phrase complète du déclenchement (échéances incluses).
    declenchement: z.string(),
    duree: z.string(),
    prime: z.string(),
    // Une phrase : ce que l'entretien produit concrètement.
    produit: z.string(),
  }),
});

const pages = defineCollection({
  loader: glob({ pattern: '*.md', base: './content/pages' }),
  schema: z.object({
    titre: z.string(),
    // Phrase de cadrage affichée sous le titre.
    chapeau: z.string(),
  }),
});

export const collections = { formats, pages };
