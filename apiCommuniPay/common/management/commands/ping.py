from django.core.management import BaseCommand

class Command(BaseCommand):
    help = "Health check command (returns 0 if Django boots)."
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("pong"))
