from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.memory_examples import seed_memory_examples


class Command(BaseCommand):
    help='Add three visibly disclosed fictional travel memories without replacing staff edits.'

    @transaction.atomic
    def handle(self,*args,**options):
        count=seed_memory_examples(apps)
        self.stdout.write(self.style.SUCCESS(f'{count} demo memories created. Existing stories were preserved.'))
