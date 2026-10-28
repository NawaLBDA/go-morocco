# Exemple Rabat

`python manage.py seed_rabat_preview` ajoute un programme de trois jours et deux départs publiés pour visualiser les cartes et la réservation. Lors de la première exécution locale du 23 octobre 2026, les dates sont le 22–24 novembre et le 22–24 décembre 2026, avec huit personnes maximum par groupe et un groupe à la fois. Ce sont des exemples à valider dans Django avant une ouverture commerciale.

Pour un nouveau tour, le programme contient huit étapes et cinq liaisons : Hassan, mausolée Mohammed V, Bouregreg, Kasbah des Oudaia, jardins andalous, panorama, Chellah et médina. Les coordonnées sont approximatives et les liaisons illustratives ; elles servent à tester le dessin de carte, pas à fournir un itinéraire routier validé. Les lieux s’appuient sur la présentation patrimoniale de [Rabat par l’UNESCO](https://whc.unesco.org/fr/list/1401/). Les textes sont propres au projet.

La commande conserve les journées déjà renseignées et les retouches ; elle complète uniquement les journées manquantes. Sur le Rabat existant, le premier jour a été conservé, puis les jours deux et trois complétés. Elle ne crée ni client, ni réservation, ni guide fictif. L’image de l’article reprend la référence de l’image Rabat existante, sans nouvel envoi de fichier. L’article est explicitement présenté comme une inspiration éditoriale d’exemple.

Dans Django : Tours → Rabat → activités et liaisons ; Départs → dates, taille du groupe et programme ; Blog posts → article et image. Les réservations utilisent les dates du départ sélectionné sur la carte. Aucun sélecteur de départ n’est affiché dans le formulaire.
