# Contact uniquement par email

Adresse publique provisoire : **contact@culturehoptours.com**. Les liens WhatsApp du pied de page, de la page contact et de la réservation ainsi que le bouton flottant sont retirés. Le numéro WhatsApp des réglages publics est vidé et masqué dans le formulaire des réglages globaux.

Cette modification ne crée pas une boîte mail. Pour recevoir les emails adressés à cette adresse, créer la boîte ou un alias auprès du fournisseur du domaine et configurer les enregistrements DNS nécessaires. L’adresse d’expédition vérifiée et les destinataires opérationnels déjà configurés sont conservés. Les messages du formulaire restent enregistrés dans Django en cas de défaut d’envoi.

La migration `0049_email_only_contact` applique l’adresse publique à l’installation existante. Les paramètres de messagerie restent modifiables dans Django et dans les variables d’environnement du serveur.
