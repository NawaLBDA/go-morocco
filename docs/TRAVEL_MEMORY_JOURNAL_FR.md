# Page Travel stories & memories

La page `/blog/` est un journal indépendant : aucune carte de départ, aucun tarif, aucun compteur de réservations. L’accueil conserve le catalogue de voyages ; les mémoires se consultent via la navigation « Travel stories ».

Trois récits fictifs servent à tester la présentation : Rabat, Marrakech et Lagos. Chaque carte et chaque détail indique « Demo memory », avec la mention de récit fictif et d’image générée. Aucune personne fictive n’a été créée comme guide réel, client, réservation ou avis client. Les articles de planification existants sont conservés dans Django sous « Planning inspiration » et retirés de ce journal de souvenirs.

Dans Django → Blog posts : titre, pays, ville, date du souvenir, type d’article, texte et couverture sont modifiables. Le champ Image téléversé prend priorité sur l’image initiale. Pour convertir un exemple en récit réel, remplacer le texte et les images par vos éléments authentiques, puis décocher « Is demo ». Les exemples gardent sinon leur repère visible et ne sont pas indexés comme souvenirs réels.

Les migrations `0051` et `0052` ajoutent les champs et les trois exemples une seule fois sur Render. Sur un autre environnement : `python manage.py seed_memory_examples`. Cette commande conserve les retouches.

Les trois assets ont été générés avec l’outil intégré **imagegen**, inspectés et enregistrés dans le projet :

- `static/img/demo-memory-rabat.webp`
- `static/img/demo-memory-marrakech.webp`
- `static/img/demo-memory-lagos.webp`

Les coordonnées de contact restent uniquement par email. Les réservations et les voyages déjà configurés ne sont pas modifiés.

## Prompts finaux

### rabat

Original photorealistic editorial travel illustration for a FICTIONAL demo travel memory, landscape 3:2 composition. In a Rabat-inspired Moroccan riverside setting with whitewashed kasbah architecture, a welcoming fictional female local guide in contemporary modest casual clothes shares a moment with four adult travelers of varied ages and backgrounds. Candid small-group interaction, relaxed smiles, natural hand gestures, warm late-afternoon light, blue river and simple white architecture visible. Medium-wide environmental photo, believable human proportions and hands, documentary aesthetic but entirely fictional people, not based on real guides or customers. No brands, no readable signs, no text, no logo, no watermark. Leave comfortable room around people for responsive crops. This will be clearly labelled as an AI-generated demo image, never evidence of a real company trip.

### marrakech

Original photorealistic editorial travel illustration for a FICTIONAL demo travel memory, landscape 3:2 composition. A Marrakech-inspired ochre courtyard craft workshop, a fictional Moroccan artisan and a fictional male local guide talking with four adult travelers of varied backgrounds near handmade ceramic bowls and woven baskets. Natural lively conversation, a shared discovery, beautiful textured plaster and greenery, soft warm daylight, candid medium-wide composition. Contemporary tasteful clothing, respectful natural atmosphere, anatomically realistic people and hands. Entirely fictional people, no actual guide or customer identities, no copied identifiable artwork. No brands, readable text, logo or watermark. This will be clearly labelled as an AI-generated demo image, not documentation of a real company trip.

### lagos

Original photorealistic editorial travel illustration for a FICTIONAL demo travel memory, landscape 3:2 composition. A bright contemporary Lagos-inspired creative studio with locally inspired original abstract textile designs and geometric artwork. A fictional Nigerian woman guide in contemporary clothing shares a friendly moment with a small group of four adult travelers of varied backgrounds, one Nigerian artisan showing a colorful original patterned fabric. Natural candid conversation and connection, genuine-looking relaxed expressions, warm tropical window light, elegant uncluttered interior, vibrant restrained colors, medium-wide environmental view. Realistic human anatomy and hands. Entirely fictional people, not actual company guides or customers. No recognizable existing artworks, brands, text, logos or watermark. Clearly AI-generated demo illustration for a sample story, not evidence of a real trip.
