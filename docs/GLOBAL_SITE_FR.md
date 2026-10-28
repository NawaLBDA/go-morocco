# Site international — guide de prise en main

Le domaine actuel est conservé. Le projet sert désormais une seule marque et une seule administration (`/admin/`). L’Irlande est conservée dans la base mais inactive pour le lancement. Les comptes et réservations existants sont conservés.

## Gérer les pays

Dans **Countries**, ajouter un nom et un identifiant, une image, une introduction, puis activer le pays lorsque son contenu est prêt. Chaque destination, circuit, article, promotion, contenu et configuration de notification est rattaché à un pays. Les galeries, activités, départs et réservations héritent du pays de leur parent.

La relation `region` utilise une clé étrangère protégée vers le catalogue des pays. Le champ historique `country` est conservé pour les intégrations existantes, synchronisé à l’enregistrement et contrôlé en base. Le pays du profil utilisateur reste une information personnelle et ne choisit plus le site affiché. Ne pas modifier les identifiants de pays existants ni changer `country` avec une mise à jour SQL isolée.

Le mode **Uses scheduled departures**, activé par défaut, utilise des départs publiés, des prix journaliers et un calendrier privé par pays. Le mode flexible nocturne de l’ancien contenu irlandais est conservé. Les réservations simultanées dans deux pays différents sont indépendantes. Dans un même pays en mode programmé, la règle existante d’un seul groupe privé à la fois est conservée ; la capacité indique la taille maximale de ce groupe, pas des places vendues individuellement.

## Accueil et images

**Global website settings** : marque, titre, sous-titre, image principale, email, WhatsApp et décoration saisonnière. **Countries** : image et présentation du pays. Les images des circuits restent remplaçables dans **Tours**. Les images existantes servent de valeurs initiales ; le nouveau visuel d’accueil est livré dans `static/img/global-hero.webp`.

Le visuel d’accueil a été créé avec l’outil imagegen intégré. Prompt : photographie éditoriale de dunes du Sahara à la lumière dorée, petite caravane sur la droite, tons terre cuite et ciel bleu pâle, espace calme à gauche pour le titre, sans texte ni logo. Il s’agit d’une illustration de destination, pas d’une photographie documentaire d’un circuit réellement effectué.

## Départs et prix

Créer le circuit et ses activités, puis un départ avec dates, capacité et programme. Publier après vérification. L’accueil classe automatiquement les départs futurs publiés par mois. Les filtres pays, mois et recherche se combinent.

**Promotions** : pourcentage entre 0 et 100, pays, activation, application à tous les circuits du pays, dates de début et de fin inclusives, décoration Christmas. Les périodes permettent les offres saisonnières. Une promotion générale et une remise propre au circuit ne se cumulent pas : la plus élevée s’applique au prix de base. Les suppléments restent facturés séparément. La remise groupe de 10 % s’applique au total pour plus de cinq personnes, comme indiqué dans les notes. Le prix accepté est conservé sur la réservation.

L’offre initiale **Christmas & New Year** est de **40 % du 1er décembre 2026 au 5 janvier 2027**, pour le Maroc. Elle n’apparaît pas en octobre. Modifier ses dates dans Django pour prévisualiser la décoration. La décoration peut aussi être désactivée dans les réglages globaux.

## Accessibilité et vidéos

Cocher **Deaf only** pour réserver la visibilité et la réservation d’un circuit aux comptes ayant volontairement déclaré ce statut (et au personnel). Les accès directs et les appels de réservation sont contrôlés. Ajouter le lien d’une vidéo explicative dans le circuit. Les articles acceptent aussi un lien de vidéo, hébergée à l’extérieur pour limiter la charge serveur. Publier un article avec ce lien pour le faire apparaître parmi les histoires de l’accueil. Les liens sont présentés sans lecture automatique.

## Contacts et équipe

Les réglages de contact et de notifications existants restent disponibles par pays dans la même administration. Ajouter les emails de l’équipe et les numéros WhatsApp dans **Booking notification settings**. Les identifiants du fournisseur email, de Twilio et le modèle WhatsApp approuvé doivent être configurés sur le serveur pour des livraisons réelles. Aucun compte fournisseur ni message externe n’a été créé ou envoyé pendant cette modification. L’interface du chatbot a été retirée de la navigation publique ; les anciens endpoints restent disponibles pour compatibilité.

## Initialisation et déploiement

```powershell
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed_global_site
.venv/Scripts/python.exe manage.py runserver
```

L’initialisation est réexécutable et ne remplace pas les modifications du personnel. Les trois nouveaux exemples de circuits ont des prix indicatifs et des départs en brouillon : les vérifier avant publication. Le démarrage Render appelle également cette initialisation. Aucune mise en production n’a été lancée.

Référence de structure consultée : https://handson.travel/2026-tours/ — présentation de circuits internationaux avec dates et tailles de groupes. L’identité visuelle, les textes et le code de cette refonte sont propres au projet.


## Prompt exact du visuel généré

Outil : imagegen intégré. Sortie utilisée : `static/img/global-hero.webp` (WebP optimisé à partir du PNG généré).

> Generate a photorealistic editorial travel photograph for a premium international travel agency website hero. Wide landscape 3:2 composition. Morocco, rolling Sahara dunes near Merzouga at golden hour, distant rugged Atlas-like horizon in soft atmospheric haze, a tiny caravan of camels with local guides along the ridge on the right third. Warm terracotta sand, apricot sunlight, pale blue sky. Elegant natural photography, tangible sand ripples, cinematic depth, no fantasy buildings, no text, no logos, no borders. Left half calm and uncluttered for overlaid headline. This is an evocative destination illustration, not a documentary claim. Save generated image for use in local project.

`static/img/morocco-marrakech-starter.webp` reprend l’image Marrakech déjà présente dans le catalogue du projet, optimisée pour le circuit initial. Les autres images initiales proviennent des ressources existantes.


## Mosaic Journeys et les équipes de guides

La marque est **MOSAIC JOURNEYS**, avec le slogan **Many cultures. Unforgettable journeys.** et les horizons **Africa • Caribbean • Middle East • Ireland**. Ces horizons expriment la marque ; seuls les pays activés dans Countries sont proposés à la réservation. Le domaine et les coordonnées de contact existants sont conservés.

Dans **Countries → choisir un pays → Guides**, ajouter autant de membres que nécessaire : nom, photo, description, statut actif et ordre d’affichage. Le menu **Guides** permet aussi de gérer tous les membres et de filtrer par pays.

Chaque page de réservation affiche une section **Meet your local team**. Par défaut, elle présente les membres actifs du pays du circuit. Dans **Tours → Guiding team**, sélectionner un ou plusieurs guides pour présenter une équipe propre au circuit. Seuls les guides du même pays peuvent être associés. Les membres inactifs ne sont jamais affichés. Sans équipe renseignée, un message invite à contacter l’agence ; aucun faux nom ou portrait n’est ajouté. La composition finale est confirmée avec la réservation.

La marque, le slogan et la liste des horizons restent modifiables dans **Global website settings**.

## Départs, groupes et listes d’attente

Les règles de réservation ont été étendues : capacité simultanée du pays, limite par départ, affectation des guides et liste d’attente. La valeur initiale reste un seul groupe. Les nouvelles options et les décisions par email sont expliquées dans [le guide des départs et listes d’attente](DEPARTURES_WAITLIST_FR.md).
