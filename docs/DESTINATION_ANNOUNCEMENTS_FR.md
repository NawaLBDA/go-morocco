# Destinations en préparation

Les quatre destinations de départ sont Nigeria, Morocco, Ireland et Jamaica.
Nigeria et Jamaica sont affichés comme « In the works », sans prix ni possibilité de réservation. Les exemples déjà saisis restent dans Django ; les réservations existantes restent conservées.

Dans Django → Countries, « Is active » rend le pays visible. « Coming soon » conserve uniquement l'annonce et empêche les nouvelles réservations et demandes de liste d'attente. Les récits de ces pays sont masqués pendant cette phase.

Lorsque le pays est prêt, renseigner les programmes, prix et dates, vérifier les contenus de démonstration puis désactiver « Coming soon ». Les dates doivent également être publiées pour apparaître dans le catalogue.

La migration de lancement ne crée aucun prix ou programme pour Jamaica ou Ireland. Elle conserve les contenus existants de Morocco et met à jour le texte des destinations du footer.
