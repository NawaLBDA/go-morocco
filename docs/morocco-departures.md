# Départs planifiés — site Maroc

Le visiteur choisit un départ publié. Il ne saisit plus librement les dates de sa réservation.

## Configurer un tour

1. Dans `/admin/`, ouvrir **Tours**, puis le tour concerné.
2. Renseigner le **prix par personne et par jour**.
3. Régler **Maximum days per departure** : 5 par défaut, modifiable à 6, 19 ou une autre durée. Les dates de début et de fin sont incluses dans cette limite.
4. Ajouter les activités dans **Tour itinerary**, avec leurs descriptions, lieux, horaires et images. Elles constituent la liste d'activités disponibles pour ce tour.
5. Dans **Scheduled departures**, ajouter les dates de début et de fin. Pour une seule journée, saisir la même date dans les deux champs. Enregistrer d'abord le départ comme brouillon.
6. Ouvrir le lien du départ enregistré, ou passer par **Tour departures** dans l'admin. Une ligne de programme est créée pour chaque date, initialement remplie avec les activités du même jour du tour.
7. Pour chaque jour, sélectionner les activités et éventuellement un titre. Décocher **Include this day** pour retirer ce jour du séjour, de la durée facturée et du prix.
8. Cocher **Is published** et enregistrer. Au moins un jour doit être inclus. Le départ apparaît alors sur la page publique du tour s'il n'est pas passé.

Les départs ne sont pas récurrents : chaque plage possède des dates complètes (jour, mois, année). Ajouter plusieurs départs pour proposer plusieurs périodes et programmes.

## Réservation et prix

- Une journée incluse = un jour facturé, même si début et fin sont identiques.
- Exemple : départ du 10 au 14, jour 12 désactivé = quatre jours facturés. Le programme indique les dates incluses ; le guide reste réservé du 10 au 14 pour ce groupe.
- Prix de base = tarif journalier × jours inclus × voyageurs, avec les suppléments choisis et la remise existante de 10 % à partir de cinq voyageurs.
- Une demande en attente ou une réservation confirmée bloque toute la période dans toutes les villes du Maroc, y compris les dates de début et de fin. Un autre groupe peut partir le lendemain de la fin.
- Le serveur vérifie à nouveau le départ et les disponibilités à l'envoi. Deux visiteurs ne peuvent pas réserver simultanément la même période.
- Un départ déjà réservé ne peut plus changer de dates ou de programme dans l'admin. Créer un nouveau départ pour un nouveau programme.

## Mise en service

La migration `0032` ajoute les réglages et les départs. Elle ne crée pas de disponibilités fictives et ne modifie pas le montant des réservations existantes. Il faut publier les départs réels dans l'admin pour que les visiteurs puissent réserver.

En local : `python manage.py migrate`, puis `python manage.py runserver`.
Le démarrage Render configuré dans le dépôt exécute déjà les migrations.

Les réservations antérieures conservent leurs prix et leur mode de calcul historiques. Le site Irlande conserve son fonctionnement de réservation existant.
