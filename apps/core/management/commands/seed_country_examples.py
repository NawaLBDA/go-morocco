from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.catalogue_examples import seed_examples


class Command(BaseCommand):
    help = 'Add editable Morocco and Nigeria examples, including Deaf-labelled departures, without replacing staff content.'

    def add_arguments(self, parser):
        parser.add_argument('--activate-countries', action='store_true', help='Activate Morocco and Nigeria for this explicit catalogue launch.')

    @transaction.atomic
    def handle(self, *args, **options):
        result = seed_examples(apps, activate_countries=options['activate_countries'])
        self.stdout.write(self.style.SUCCESS(str(result)))
