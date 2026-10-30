# Acompte avant approbation

Les packs acceptent par défaut 1 à 20 voyageurs. Le minimum et le maximum restent modifiables dans Django → Tours.

La fonction d'acompte est **désactivée par défaut**. Le minimum du pack commande son application : minimum 1, aucun acompte ; minimum supérieur à 1, l'admin peut l'activer ou le désactiver. Aucun caractère non remboursable n'est ajouté et aucun débit automatique n'est effectué.

Dans Tours → Group size and deposit :

- Minimum travelers per group et Deposit enabled sont côte à côte : la case active la règle pour les nouvelles demandes uniquement si le minimum est supérieur à 1.
- Maximum travelers per group reste configurable indépendamment.
- Deposit amount : montant de l'acompte.
- Deposit per person : cocher uniquement si le montant s'applique à chaque personne ; sinon il concerne toute la réservation.

Parcours lorsque la règle est activée : demande reçue → acompte en attente → acompte reçu → approbation par l'équipe → paiement final. L'acompte fait partie du prix total, il ne s'y ajoute pas. Le reçu d'acompte ne marque pas la totalité du séjour comme payée.

L'admin vérifie le paiement auprès de sa banque puis utilise « Record verified deposit received » dans la liste des réservations, ou l'action équivalente dans Django. La date et l'agent qui enregistre la réception sont conservés. L'approbation est bloquée tant que l'acompte requis n'est pas enregistré. L'email et le téléphone du voyageur sont affichés pour faciliter le contact.

Le voyageur voit le montant et le statut dans My reservations. Les emails de demande, de réception de l'acompte, d'approbation et de paiement final utilisent le fournisseur d'envoi configuré sur le serveur. Un fournisseur doit être actif pour qu'ils soient réellement distribués.

Exemple : séjour à 20 000 USD, acompte vérifié de 500 USD → solde de 19 500 USD. Les anciens dossiers n'ont pas d'acompte imposé rétroactivement. Les conditions d'annulation et de remboursement restent à définir par l'entreprise.
