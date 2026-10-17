from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Show service configuration without revealing credentials. Optional AI probe makes one provider request.'

    def add_arguments(self, parser):
        parser.add_argument('--probe-ai', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(f'Email backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Verified sender must be configured: {settings.DEFAULT_FROM_EMAIL}')
        for name in ['RESEND_API_KEY', 'HF_API_TOKEN', 'OPENAI_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM']:
            self.stdout.write(f'{name}: {"configured" if getattr(settings, name, "") else "missing"}')
        self.stdout.write(f'Hugging Face model: {settings.HF_MODEL}')
        self.stdout.write(f'OpenAI model: {settings.OPENAI_MODEL}')
        if options['probe_ai']:
            from apps.core.assistant_service import stream_answer
            try:
                answer = ''.join(stream_answer('Reply briefly.', 'Say hello.'))
            except RuntimeError:
                raise CommandError('AI probe failed. Review provider status codes in logs, token permissions, model availability and account credits.')
            self.stdout.write(self.style.SUCCESS(f'AI provider responded ({len(answer)} characters).'))
