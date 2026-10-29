# Destinataires des emails

- **Contact du site : info@culturehoptours.com.** Les messages du formulaire de contact y sont envoyés. La réponse revient directement à l’email saisi dans ce formulaire.
- **Réservations : omasampson@culturehoptours.com + l’email du compte voyageur.** Demande reçue, approbation, paiement reçu, refus, annulation et fin de voyage sont notifiés. Les réponses du voyageur reviennent à la boîte de réservation, pas à la boîte info.
- **Décisions de liste d’attente :** email au demandeur, copie cachée à l’administration des réservations et réponse vers cette administration.

Les deux adresses sont configurables dans Global website settings. Les règles de contact par pays et les destinataires administratifs supplémentaires restent disponibles. La migration `0053_separate_email_inboxes` met à jour les adresses existantes selon la demande, sans modifier les mots de passe, les réservations ou l’expéditeur déjà vérifié.

Les tests utilisent une boîte mémoire : ils vérifient les destinataires, les réponses, la copie cachée et l’absence de doublons, sans envoyer d’emails réels. Une acceptation du fournisseur n’est pas une preuve de réception dans la boîte finale.

Le réglage MX montré dans la capture concerne la réception des emails du domaine. L’application Render doit séparément disposer d’un fournisseur d’envoi configuré : SMTP autorisé ou service d’envoi via HTTPS, avec ses identifiants dans les variables d’environnement du serveur. Le projet prend déjà en charge SMTP et Resend. Le champ `sender_email` doit correspondre à un expéditeur vérifié auprès de ce fournisseur. Les identifiants ne sont jamais placés dans le code ou dans Git.

Le projet local utilise actuellement le backend console, sans identifiants SMTP ni clé Resend. La réception réelle dans les boîtes ne peut pas être confirmée avec les seuls tests locaux. Les messages du formulaire sont conservés dans Django et les notifications de réservation en échec peuvent être relancées après configuration.
