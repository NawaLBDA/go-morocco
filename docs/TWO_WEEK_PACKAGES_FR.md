# Séjours de deux semaines et pays masqués

- Le tarif public correspond au séjour complet de 14 jours **par personne** : 4 100 USD pour Morocco et 4 000 USD pour les autres circuits actuels. Le total de base est le tarif du séjour multiplié par le nombre de voyageurs, sans multiplication supplémentaire par 14.
- La capacité des nouveaux groupes est limitée à 20. Les frais optionnels restent affichés et calculés séparément. Les promotions et la remise automatique des anciens tarifs journaliers ne réduisent pas les forfaits sous le minimum demandé.
- Django → Tours : **Package price** fixe le tarif complet, minimum 4 000 USD. **Package days** vaut 14. Le tarif journalier est conservé dans une section repliée pour les anciens dossiers.
- Django → Countries : **Show this country** masque ou réaffiche le pays, ses circuits, ses récits et ses liens publics sans supprimer ses données. **Coming soon** reste une option séparée pour les annonces Nigeria/Jamaica.
- Les réservations existantes conservent leurs dates, leur programme et leur montant. Les départs libres du catalogue passent à 14 jours et 20 personnes. Les dates peuvent être décalées pour éviter les chevauchements avec d'autres groupes. Les journées ajoutées portent « programme to be confirmed » et doivent être renseignées par l'équipe.
- La migration de contenu s'applique automatiquement sur Render. Elle ne crée ni utilisateur, ni réservation, ni paiement. Les données restent modifiables dans Django.
- Le logo complet (CH + nom + slogan) est un seul SVG, décliné en version claire pour le footer et sombre pour l'en-tête.
