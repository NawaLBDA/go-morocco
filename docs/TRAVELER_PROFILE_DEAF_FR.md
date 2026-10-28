# Départs réservés et espace voyageur

Dans Django, cocher **Designed for deaf travelers** sur un tour ou un d?part pour afficher le badge ? For deaf travelers ? Everyone welcome ? et son ic?ne. Ce libell? est informatif : tous les voyageurs peuvent consulter et r?server, quel que soit leur statut sourd. Le nom technique historique du champ `deaf_only` est conserv? pour pr?server les donn?es existantes.

La connexion reste obligatoire pour r?server. Le statut d?clar? ? l?inscription est conserv? dans le profil, sans bloquer la r?servation ni la liste d?attente. Les contr?les de capacit?, de dates et de disponibilit? continuent de s?appliquer.

**My profile**, dans la navigation, donne accès aux coordonnées et au statut en lecture seule. Aucun formulaire ne permet de modifier nom, email, téléphone, pays, code postal ou statut sourd. Les POST sont refusés. Les éventuelles corrections passent par l’équipe.

**My reservations**, dans le profil, contient uniquement les réservations de la personne connectée, avec référence, voyage, dates, voyageurs, total, statut et état de paiement. Cette page est en lecture seule et paginée. Elle n’affiche pas les notes administratives. La confirmation d’une nouvelle demande redirige vers cette liste. Les récapitulatifs personnels détaillés ont été retirés des pages de tour ; un lien vers My reservations y reste disponible lorsqu’une demande existe déjà.

Le mot de passe se réinitialise par email avec les vues sécurisées de Django : demande de lien, jeton temporaire, choix du nouveau mot de passe. Le jeton est invalidé après utilisation et le mot de passe ne change pas lors d’une simple demande d’email. La réponse à la demande ne révèle pas si un compte existe. L’email reprend le nom de marque et l’expéditeur configurés. Comme les autres emails, la réception réelle nécessite un fournisseur d’envoi configuré.

Migration : `0045_deaf_only_departures`. Aucun départ existant n’a été rendu restreint automatiquement.
