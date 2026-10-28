# Catalogue initial Maroc et Nigeria

Ajout demandé pour Render : Rabat, Marrakech, Tanger (Tangier), Lagos et Abuja. Chaque voyage reçoit six étapes sur trois jours, trois liaisons illustratives et deux départs publiés : un ordinaire et un portant « Deaf · Everyone welcome ». Tous les comptes peuvent réserver les deux types de départ.

Les tarifs d’exemple par personne et par jour sont respectivement 100, 145, 110, 135 et 125 USD. Maximum par groupe : huit personnes au Maroc, six au Nigeria. Un groupe simultané par départ, sous réserve du plafond existant de l’équipe du pays. Les dates commencent environ un mois après l’initialisation ; les créneaux déjà occupés par des réservations actives sont évités. Les exemples ne créent aucun client, aucune réservation, aucun paiement et aucun guide fictif.

Les descriptions précisent qu’il s’agit d’un programme initial à confirmer par l’équipe. Les coordonnées et les liaisons sont approximatives pour illustrer la carte. Les accès, prix, transferts, disponibilités et compétences en langue des signes ne sont pas présentés comme vérifiés. Ils doivent être revus dans Django avant confirmation commerciale.

Les voyages existants et les réservations ne sont pas modifiés. Les nouveaux voyages ont des slugs réservés `demo-*-culture` ; une nouvelle exécution conserve les retouches et ne recrée pas les dates supprimées. Les images de ville existantes sont reprises si disponibles ; le Nigeria utilise sinon son visuel d’inspiration déjà présent. Deux articles d’inspiration sont ajoutés, sans faux récits de groupes ayant voyagé.

La migration `0050_render_country_examples` réalise ce lancement une seule fois sur Render, à l’aide de sa variable officielle [`RENDER=true`](https://render.com/docs/environment-variables). Elle active le Maroc et le Nigeria. Sur une autre installation : `python manage.py seed_country_examples --activate-countries`. Sans l’option d’activation, la commande conserve les pays désactivés par l’équipe.

Repères utilisés pour rédiger les textes originaux : [patrimoine de Rabat](https://whc.unesco.org/en/list/1401), [médina de Marrakech](https://whc.unesco.org/en/list/331/), [centres de la Nigerian Conservation Foundation](https://ncfnigeria.org/our-centers/). Ces sources servent de contexte, pas de confirmation d’accès pour des dates données.
