# Configuration email, WhatsApp et assistant

Les destinataires se règlent dans Django. Les clés des fournisseurs se règlent dans l'hébergement, jamais dans GitHub ni dans une conversation.

## 1. Email sur Render, y compris l'offre gratuite

L'offre gratuite de Render bloque les ports SMTP 25, 465 et 587. Utiliser l'envoi HTTPS proposé dans ce projet.

1. Créer un compte Resend et ajouter le domaine d'envoi que vous contrôlez.
2. Ajouter chez votre gestionnaire DNS les enregistrements demandés par Resend, puis attendre la validation du domaine.
3. Créer une clé API avec la permission d'envoyer des emails.
4. Dans Render, ouvrir le service web du site, puis **Environment**. Ajouter :

```text
EMAIL_BACKEND=apps.core.email_backend.ResendEmailBackend
RESEND_API_KEY=<votre clé privée>
DEFAULT_FROM_EMAIL=Basma <notifications@votre-domaine-verifie>
```

5. Enregistrer puis redéployer le service. Remplacer le domaine d'exemple par le domaine réellement validé. Une adresse Gmail de réception peut recevoir les messages ; elle n'est pas un domaine d'envoi que vous pouvez valider comme votre propre domaine.
6. Dans **Admin > Contact email settings**, saisir l'adresse qui reçoit les demandes d'information et d'aide.
7. Dans **Admin > Booking notification settings**, saisir les adresses du personnel destinataire des réservations, une par ligne. Chaque personne reçoit un email séparé.
8. Envoyer une demande d'aide et créer une réservation de vérification. Vérifier les boîtes de réception, les indésirables et le journal **Booking notifications**.

L'adresse de contact et la liste des destinataires des réservations sont indépendantes. Les messages de contact restent dans l'admin si l'envoi échoue. Les réservations restent enregistrées même si leurs notifications échouent.

Si un autre hébergement autorise SMTP, les variables EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS et EMAIL_USE_SSL restent utilisables avec le backend SMTP Django. Ne pas activer TLS et SSL simultanément.

## 2. Notifications WhatsApp automatiques

Un lien WhatsApp ordinaire ne permet pas d'envoyer automatiquement des notifications serveur. La fonction ajoutée utilise Twilio WhatsApp Business et un modèle approuvé.

1. Configurer un expéditeur WhatsApp Business dans Twilio. Le Sandbox sert aux essais avec des destinataires ayant rejoint ce Sandbox ; ce n'est pas une configuration de production.
2. Créer et faire approuver un modèle de notification de réservation. Utiliser ces variables :

| Variable | Valeur fournie |
| --- | --- |
| 1 | Numéro de réservation |
| 2 | Nom du titulaire du compte |
| 3 | Nom du tour |
| 4 | Dates de début et fin |
| 5 | Nombre de voyageurs |
| 6 | Montant et devise affichée |
| 7 | Téléphone du titulaire |
| 8 | Email du titulaire |

Exemple de texte à adapter et soumettre à approbation :

```text
New booking request #{{1}}.
Traveler: {{2}}. Tour: {{3}}.
Dates: {{4}}. Persons: {{5}}. Total: {{6}}.
Phone: {{7}}. Email: {{8}}.
Please review this request in Admin Reservations.
```

3. Dans Render > Environment, ajouter :

```text
TWILIO_ACCOUNT_SID=<identifiant Twilio>
TWILIO_AUTH_TOKEN=<secret Twilio>
TWILIO_WHATSAPP_FROM=whatsapp:+<numero expediteur active>
```

4. Dans **Booking notification settings**, saisir le Content SID du modèle approuvé (HX...) et les numéros des destinataires du personnel, un par ligne, au format international, par exemple +212600000000. Ces destinataires doivent avoir accepté de recevoir ces notifications.
5. Enregistrer. Une nouvelle réservation crée un envoi par canal et destinataire après l'enregistrement définitif. Modifier ou approuver une réservation ne renvoie pas automatiquement la notification initiale.

**Booking notifications** affiche Pending, Sending, Accepted by provider ou Failed. « Accepted by provider » n'est pas une confirmation de lecture ou de livraison finale. En cas d'échec, corriger la configuration puis sélectionner les lignes et utiliser **Retry pending or failed notifications**. Le détail fournisseur se vérifie dans Twilio ou Resend. Ne pas renvoyer manuellement une notification déjà acceptée.

## 3. Assistant IA

Lors du diagnostic local, le modèle Qwen/Qwen2.5-7B-Instruct a répondu HTTP 400 (indisponible pour les fournisseurs activés). Le modèle de remplacement a répondu HTTP 402 (crédits nécessaires). La clé OpenAI locale a répondu HTTP 401. Cela ne constitue pas une lecture de la configuration privée de Render.

Option Hugging Face dans Render > Environment :

```text
HF_API_TOKEN=<jeton autorisé pour Inference Providers>
HF_MODEL=Qwen/Qwen3-4B-Instruct-2507:fastest
HF_FALLBACK_MODEL=Qwen/Qwen3-4B-Instruct-2507:fastest
```

Vérifier les permissions du jeton, les fournisseurs activés et les crédits disponibles. Le modèle était répertorié par l'API des modèles lors du diagnostic ; sa disponibilité peut changer.

Si vous utilisez plutôt OpenAI, fournir une clé API valide et financée dans OPENAI_API_KEY et un modèle accessible dans OPENAI_MODEL. Retirer une ancienne clé invalide. Une clé présente ne prouve pas que le compte a accès au modèle.

Après redéploiement, dans Render Shell si disponible :

```text
python manage.py check_services
python manage.py check_services --probe-ai
```

La première commande montre les réglages sans révéler les clés. La seconde fait une courte requête réelle au fournisseur. Les journaux montrent les codes d'erreur sans afficher les secrets. Sans fournisseur disponible, le site explique l'indisponibilité et présente les tours existants au lieu d'inventer une réponse.

## 4. Validation après déploiement

- Les migrations doivent être appliquées par le démarrage du service.
- Les rubriques Sections et Country contents ne figurent plus dans l'administration. Le contenu existant n'est pas supprimé.
- Les réglages transport/hébergement ne sont plus exposés dans les formulaires admin concernés ; les anciennes réservations restent conservées.
- La déclaration Deaf utilise un interrupteur compact et facultatif.
- Le nom d'utilisateur ne donne jamais automatiquement des droits administrateur. Un administrateur existant doit attribuer les droits voulus via Users. Vérifier les comptes staff historiques : les droits déjà attribués ne sont pas révoqués automatiquement.

## Sources officielles

- Render : https://render.com/docs/free
- Resend : https://resend.com/docs/send-with-python
- Twilio : https://www.twilio.com/docs/whatsapp/tutorial/send-whatsapp-notification-messages-templates
- Hugging Face : https://huggingface.co/docs/inference-providers/hub-api
