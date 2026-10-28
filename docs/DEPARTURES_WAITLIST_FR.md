# Départs, groupes et listes d’attente — Mosaic Journeys

## Ce que voient les voyageurs

- **Find a journey / Reservations** : avec plusieurs pays actifs, la première page affiche les pays et leurs compteurs de circuits disponibles, de départs et de voyageurs réservés. Cliquer sur un pays ouvre son catalogue.
- Une **carte par plage de dates publiée** : le même circuit apparaît plusieurs fois si vous programmez plusieurs départs. Chaque carte indique ses dates, son prix par personne, le maximum par groupe, les voyageurs réservés et les groupes déjà inscrits.
- Le voyageur peut choisir un groupe plus petit que le maximum. Le serveur contrôle la taille et la capacité au moment de l’enregistrement, même si une autre personne réserve entre-temps.
- Les dates complètes restent consultables. Leur bouton ouvre le programme et la **liste d’attente**. Les demandes en attente ne réservent aucune place et ne sont pas facturées.
- Le filtre **Travel year** permet de parcourir les années publiées. Sans année sélectionnée, seuls les départs à venir sont proposés. Les anciens départs sont consultables, mais ne peuvent plus être réservés ou placés en liste d’attente.
- Les compteurs publics sont des totaux ; aucun nom ou email de client n’est publié. Les groupes en attente de validation et les groupes confirmés occupent la capacité. Pour les départs passés, les réservations terminées sont aussi comptées dans l’historique.

## Régler votre capacité dans Django

Deux réglages distincts protègent votre organisation :

| Où | Réglage | Signification |
| --- | --- | --- |
| Countries → pays | Max concurrent groups | Nombre maximum de groupes guidés simultanément dans tout le pays. Par défaut : 1. |
| Tour departures → départ | Max concurrent bookings | Nombre maximum de groupes indépendants pour ce départ précis. Par défaut : 1. |
| Tour departures → départ | Max participants | Nombre maximum de voyageurs **dans chaque groupe**, pas le total de tous les groupes. |

Exemples :

- Petite équipe : pays **1**, départ **1**, maximum **8** personnes. Un seul client réserve son groupe de 1 à 8 personnes ; les autres peuvent rejoindre la liste d’attente.
- Deux guides pouvant mener deux groupes séparés : pays **2**, départ **2**, maximum **8** personnes. Deux clients distincts peuvent réserver deux groupes, chacun de 1 à 8 personnes.
- Deux guides sur deux destinations différentes : pays **2**, chaque départ **1**. Chaque départ accueille un seul groupe, dans la limite de deux groupes simultanés dans le pays.

Les groupes sont privés : on ne vend pas automatiquement des places individuelles à plusieurs comptes dans un même groupe. Un même compte ne peut pas créer plusieurs demandes actives pour le même départ.

Une baisse des capacités est refusée dans les formulaires Django si elle rend les réservations existantes incompatibles. Les calendriers sont verrouillés pendant les écritures pour éviter que deux requêtes simultanées ne dépassent la limite.

## Affecter les guides à chaque groupe

Dans **Reservations → choisir une réservation → Assigned guides**, sélectionner un ou plusieurs membres du pays. Un guide déjà affecté à un groupe actif sur des dates qui se chevauchent ne peut pas être affecté à un autre groupe. La réservation affiche ses guides affectés ; à défaut, elle présente l’équipe du circuit ou du pays.

Augmenter une capacité n’affecte pas automatiquement les guides. Définir la limite selon vos moyens réels, puis affecter les membres disponibles dans l’administration.

## Accepter ou refuser une demande d’attente

Dans **Admin → Bookings / Admin Reservations**, la section **Waiting-list requests** présente la date, le groupe, l’email, le message et le statut. Le lien **Review current groups** aide à consulter les réservations existantes et leurs paiements.

- **Accept & email** : vérifie de nouveau la publication, les dates, la taille du groupe, l’éligibilité du compte et les deux limites de capacité. Si une place est réellement disponible, crée une réservation confirmée, sans paiement automatique, puis envoie la décision et le montant au voyageur.
- **Decline & email** : conserve les réservations existantes et informe le demandeur du refus. Vous pouvez inclure une explication ou proposer d’autres dates dans le champ de message.
- Si un autre groupe est déjà confirmé et payé, il reste protégé. Une acceptation d’attente ne le remplace jamais. Vous devez disposer d’une capacité supplémentaire réelle ou refuser la demande.
- Une décision déjà traitée n’est pas appliquée une deuxième fois. Si l’email échoue, le statut reste enregistré et **Retry email** permet de réessayer.

Les mêmes décisions sont disponibles dans **Django → Waitlist entries**, via les actions de liste. Les notifications nécessitent un fournisseur email sortant configuré et un expéditeur vérifié. Le statut indique l’acceptation par le fournisseur, pas une garantie de lecture ou de livraison. Les modes console/dummy/fichier sont identifiés comme un envoi désactivé.

## Pays, récits et moments

**Travel stories** présente d’abord les collections par pays. Un clic ouvre une page avec trois sections : **Tours**, **Stories**, **Moments**. Les articles et les images de leurs galeries sont regroupés dans leur pays. Les liens vidéo des articles restent disponibles. Le filtre d’année permet aussi de retrouver les récits des années précédentes.

Dans Django, publier les articles dans **Blog posts**, choisir leur pays, et ajouter leurs images dans la galerie de l’article. Les moments reprennent ces images sans demander une nouvelle saisie.

## Installation

La migration `0042_departure_capacity_waitlist` ajoute les limites, les affectations de guides et les demandes d’attente. Elle conserve les limites par défaut à un groupe. Elle est déjà appliquée dans l’environnement de travail ; au déploiement, exécuter `python manage.py migrate` comme habituellement.

Aucun départ fictif n’a été publié et aucun email réel n’a été envoyé pendant les tests. Les vérifications visuelles avec plusieurs pays et groupes utilisent une base de prévisualisation locale séparée.
