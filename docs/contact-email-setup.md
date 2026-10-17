# Contact form email

After deployment/migration, open **Admin → Contact email settings → Add** in the Morocco administration. Enter the destination email address and save. Edit that entry whenever the recipient changes. Ireland has its own setting in its administration.

Contact submissions are always saved in **Contact messages**. If a recipient is configured, an email notification is sent with the visitor's address as Reply-To. Failure to send does not remove the enquiry. Delivery failures are logged using the enquiry number without logging the message body.

The outgoing provider must be configured on the hosting service. The admin screen shows whether a non-delivering development backend is active. A recipient address alone cannot enable SMTP delivery.

For SMTP, configure these environment variables (credentials belong in hosting secrets, not the repository):

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`: a sender authorized by the provider
- `EMAIL_USE_TLS=true`, `EMAIL_USE_SSL=false` for the usual port 587 setup; follow your provider's requirements and never enable both.

Existing `SENDGRID_USERNAME` / `SENDGRID_PASSWORD` remain supported as fallback credentials. The default backend is console-only for development. After configuration, send a test enquiry through the public contact page and confirm both receipt in the intended inbox and its saved admin entry. No external email was sent during automated verification; tests use an in-memory mailbox.

Reservation dashboard account name and telephone come from registration. The edit dialog shows these account details separately. Guest fields default to those details for a self-booking, but a booking for another person retains its separate guest details. Missing historical phone details are displayed as **Not provided**.
