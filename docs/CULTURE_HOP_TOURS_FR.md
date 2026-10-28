# Culture Hop Tours

Nom retenu : **Culture Hop Tours**. Adresse publique canonique : **https://www.culturehoptours.com**. Le domaine sans www est également autorisé en production.

La migration `0048_culture_hop_tours_brand` met à jour le nom existant dans les réglages globaux. Le site, les métadonnées et les emails utilisent ce nom. Les coordonnées de contact et l’adresse d’expédition existantes sont conservées : aucune nouvelle adresse email n’a été inventée.

Les réglages Django, `.env.example` et `render.yaml` utilisent le nouveau domaine. Sur un hébergement déjà en service, mettre aussi à jour `MOROCCO_SITE_URL=https://www.culturehoptours.com` dans les variables d’environnement, puis rattacher les domaines www et sans www à l’application et configurer leur DNS/HTTPS. Ces opérations externes n’ont pas été effectuées depuis le projet local. Les anciens domaines restent acceptés comme alias de compatibilité ; l’URL canonique est la nouvelle adresse.
