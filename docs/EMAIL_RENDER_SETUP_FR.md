# Activer les emails sur Render

Le code prend déjà en charge Resend via HTTPS. Les MX Google existants servent à la réception : les conserver. Ne pas activer la réception Resend pour ce domaine.

1. Créer un compte Resend, ajouter `culturehoptours.com` dans Domains et activer l'envoi. Recopier exactement les enregistrements DNS proposés pour l'envoi (DKIM, SPF et MX du sous-domaine de retour). Ne pas remplacer le MX Google de `@`. Attendre que Resend confirme la vérification du domaine.
2. Créer une clé API autorisée à envoyer pour ce domaine. La conserver dans Render, jamais dans Git ou dans une conversation.
3. Dans Render → service go-morocco → Environment, ajouter :

```dotenv
EMAIL_BACKEND=apps.core.email_backend.ResendEmailBackend
RESEND_API_KEY=<clé privée créée dans Resend>
DEFAULT_FROM_EMAIL=Culture Hop Tours <info@culturehoptours.com>
```

4. Dans Django → Global website settings, vérifier : Public contact email = `info@culturehoptours.com`, Booking administration inbox = `omasampson@culturehoptours.com`. Si Sender email est renseigné, utiliser `info@culturehoptours.com` : ce champ prend priorité sur DEFAULT_FROM_EMAIL.
5. Enregistrer les variables Render et redéployer le service. Les boîtes info et omasampson doivent aussi exister comme comptes ou alias chez Google Workspace.
6. Faire un essai volontaire du formulaire de contact, puis une réservation avec un compte de test contrôlé. Vérifier les journaux Resend et les boîtes de réception, y compris les indésirables. Vérifier ensuite approbation et paiement avec des données de test ; ne pas marquer une réservation client payée pour tester.

Les notifications de réservation en échec peuvent être relancées après activation. Les anciens messages de contact conservés dans Django ne sont pas automatiquement renvoyés.

Sources : [limitations Render](https://render.com/docs/free), [domaines Resend](https://resend.com/docs/dashboard/domains/introduction).
