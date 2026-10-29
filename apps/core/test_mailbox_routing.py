from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.contrib.auth.models import User
from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import SiteSettings, ContactEmailSettings, BookingNotificationSettings, ContactMessage, Tour, Destination, Reservation, TourDeparture, WaitlistEntry
from .contact_email import notify_contact
from apps.reservations.waitlist import send_decision_email


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='verified@example.com')
class MailboxRoutingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('mail-recipient',email='traveler@example.com')
        self.tour=Tour.objects.create(title='A cultural journey',destination=Destination.objects.create(name='Rabat'),price_per_night=100)
        self.start=timezone.localdate()+timedelta(days=90)

    def book(self,offset=0):
        start=self.start+timedelta(days=offset)
        return Reservation.objects.create(user=self.user,tour=self.tour,start_date=start,end_date=start+timedelta(days=2),total_price=300,payment_method='transfer')

    def assert_booking_recipients(self):
        self.assertEqual(len(mail.outbox),2)
        self.assertEqual({m.to[0] for m in mail.outbox},{'traveler@example.com','omasampson@culturehoptours.com'})
        self.assertTrue(all('info@culturehoptours.com' not in m.to for m in mail.outbox))
        traveler=next(m for m in mail.outbox if m.to==['traveler@example.com'])
        self.assertEqual(traveler.reply_to,['omasampson@culturehoptours.com'])

    def test_general_contact_uses_info_even_without_country_configuration(self):
        enquiry=ContactMessage.objects.create(country='',name='Traveler',email='traveler@example.com',subject='A question',message='Please help.')
        self.assertTrue(notify_contact(enquiry))
        self.assertEqual(mail.outbox[0].to,['info@culturehoptours.com'])
        self.assertEqual(mail.outbox[0].reply_to,['traveler@example.com'])
        self.assertEqual(mail.outbox[0].from_email,'verified@example.com')

    def test_requested_approved_and_paid_go_to_account_owner_and_booking_admin(self):
        with self.captureOnCommitCallbacks(execute=True):booking=self.book()
        self.assert_booking_recipients()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            booking.status='booked';booking.save()
        self.assert_booking_recipients()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            booking.payment_status='paid';booking.save()
        self.assert_booking_recipients()

    def test_declined_cancelled_and_completed_statuses_notify_both_without_duplicates(self):
        for index,status in enumerate(['rejected','cancelled','completed']):
            booking=self.book(offset=index*10)
            mail.outbox.clear()
            with self.captureOnCommitCallbacks(execute=True):
                booking.status=status;booking.save(update_fields=['status'])
            self.assert_booking_recipients()
            with self.captureOnCommitCallbacks(execute=True):
                booking.admin_note='A routine edit';booking.save()
            self.assertEqual(len(mail.outbox),2)

    def test_waitlist_decision_copies_booking_admin_without_disclosing_extra_recipient_to_traveler(self):
        departure=TourDeparture.objects.create(tour=self.tour,start_date=self.start,end_date=self.start+timedelta(days=2),is_published=True)
        entry=WaitlistEntry.objects.create(user=self.user,departure=departure,num_persons=1,email=self.user.email,status='rejected')
        send_decision_email(entry.pk)
        self.assertEqual(mail.outbox[0].to,['traveler@example.com'])
        self.assertEqual(mail.outbox[0].bcc,['omasampson@culturehoptours.com'])
        self.assertEqual(mail.outbox[0].reply_to,['omasampson@culturehoptours.com'])

    def test_data_migration_updates_existing_routing_without_replacing_verified_sender(self):
        SiteSettings.objects.update_or_create(pk=1,defaults={'support_email':'old@example.com','booking_email':'old-booking@example.com','sender_email':'verified@example.com'})
        contact=ContactEmailSettings.objects.create(country='morocco',recipient_email='old-contact@example.com')
        config=BookingNotificationSettings.objects.create(country='morocco',email_recipients='old-admin@example.com')
        module=import_module('apps.core.migrations.0053_separate_email_inboxes')
        module.configure_requested_inboxes(apps,SimpleNamespace(connection=connection))
        site=SiteSettings.objects.get(pk=1);contact.refresh_from_db();config.refresh_from_db()
        self.assertEqual(site.support_email,'info@culturehoptours.com')
        self.assertEqual(site.booking_email,'omasampson@culturehoptours.com')
        self.assertEqual(site.sender_email,'verified@example.com')
        self.assertEqual(contact.recipient_email,site.support_email)
        self.assertEqual(config.email_recipients,site.booking_email)
