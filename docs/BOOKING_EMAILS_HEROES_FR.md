# Notifications, inscription et visuels d’accueil

## Réglages des emails

Dans **Global website settings**, `Sender email` est réservé à votre future adresse professionnelle. Il est volontairement vide pour le moment : le serveur conserve son `DEFAULT_FROM_EMAIL`. Après l’achat de l’adresse, renseigner une adresse vérifiée auprès du fournisseur d’envoi et configurer SMTP ou Resend sur le serveur. Le champ Django ne crée pas une boîte mail et ne configure pas ses identifiants.

La boîte de l’équipe est celle de **Contact email settings** pour le pays du voyage. En l’absence de ce réglage, l’adresse support globale est utilisée. Les destinataires supplémentaires de **Booking notification settings** restent pris en compte. Les réponses des voyageurs reviennent à la boîte de contact du pays. Le nom de marque et le contact sont repris automatiquement.

Trois événements envoient chacun un email au voyageur et à l’équipe :

- Création de réservation : demande reçue, en attente d’approbation, pas de paiement à effectuer avant accord.
- Passage à « booked » : approbation et informations sur la suite du paiement, sans prétendre que le paiement a été reçu.
- Passage à « paid » : confirmation du paiement enregistré.

Chaque email possède une mise en page HTML et une alternative texte. Il contient la référence, les dates, le nombre de voyageurs, le montant et le mode de paiement. Les informations du voyage sont conservées au moment de la mise en file. Les envois partent après validation de la transaction de base de données. Une simple modification ne renvoie pas le même événement. Les décisions de liste d’attente conservent également leur message spécifique avec la note de l’équipe.

Dans **Booking notifications**, filtrer par événement, destinataire et statut. En cas d’échec, la réservation est conservée ; corriger la configuration puis utiliser « Retry pending or failed notifications ». « Accepted by provider » signifie accepté par le fournisseur, sans garantir la réception dans la boîte finale. Les tests utilisent une boîte mémoire, sans envoi réel. Aucun email réel de réservation n’a été envoyé pour vérifier cette modification.

Le webhook Stripe exige désormais `STRIPE_WEBHOOK_SECRET` et une signature valide avant d’enregistrer un paiement. Les paiements espèces/virement continuent d’être enregistrés par l’équipe dans l’administration.

## Inscription et formulaire

L’inscription impose un email valide côté serveur et côté navigateur. Une réservation exige un compte connecté, y compris via le service de création. Le voyageur retrouve son lien de réservation après le parcours connexion/inscription. Saisir un nombre supérieur au maximum du départ ramène immédiatement le champ à ce maximum ; le serveur conserve son contrôle indépendant.

Les messages d’approbation et de disponibilité sont présentés dans un toast fermable. Les erreurs bloquantes restent également près du formulaire. Les notifications disparaissent après dix secondes et peuvent être fermées immédiatement.

## Carrousel d’accueil

Dans **Global website settings → Homepage hero slides**, ajouter une slide avec pays, titre, sous-titre, légende, image, activation et ordre. Le même modèle est accessible directement dans **Homepage hero slides**. Une image téléversée remplace le visuel de départ. Les boutons permettent de naviguer et mettre en pause ; la préférence système de réduction des animations désactive la lecture automatique.

`python manage.py seed_home_heroes` prépare le Maroc et le Nigeria sans remplacer les retouches. Le Nigeria reste inactif pour les réservations ; sa slide est une inspiration avec lien vers le contact. Ajouter une slide ne rend pas un pays réservable.

Le Maroc réutilise l’image d’accueil existante. Le visuel Nigeria est une image illustrative générée avec l’outil intégré **imagegen**, inspectée puis enregistrée dans [static/img/nigeria-hero.webp](../static/img/nigeria-hero.webp). Il ne s’agit pas d’une photographie documentaire d’un voyage réalisé. La légende le précise.

Prompt final utilisé :

> Use case: photorealistic-natural. Asset: wide website hero photograph for Mosaic Journeys, Nigeria destination inspiration. Create a refined, natural travel editorial image of lush green Nigerian tropical landscape with an expansive monolithic granite outcrop inspired by the landscape around Abeokuta, warm late-afternoon light, abundant palms and green trees, subtle distant low-rise city rooftops. Wide landscape composition, realistic photographic detail, generous uncluttered dark green foliage and sky on the left for an HTML headline overlay. Optimistic welcoming atmosphere, restrained natural color, no text, no logos, no watermark, no identifiable people. This is an illustrative travel visual, not documentary evidence of a guided trip.

Migration : `0043_booking_lifecycle_and_home_heroes`. Les réglages existants d’email et les identifiants du fournisseur n’ont pas été remplacés.
