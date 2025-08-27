from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apiCommuniPay.common.models import ChatLinkIntent

class Command(BaseCommand):
    help = "Expire and purge ChatLinkIntent rows"

    def add_arguments(self, p):
        p.add_argument("--expire", action="store_true")
        p.add_argument("--delete-older-days", type=int, default=7)

    def handle(self, *args, **o):
        now = timezone.now()
        if o["expire"]:
            n = ChatLinkIntent.objects.filter(
                status=ChatLinkIntent.Status.PENDING,
                expires_at__lte=now,
            ).update(status=ChatLinkIntent.Status.EXPIRED)
            self.stdout.write(f"Expired: {n}")
        cutoff = now - timedelta(days=o["delete_older_days"])
        d, _ = (ChatLinkIntent.objects
                .exclude(status=ChatLinkIntent.Status.PENDING)
                .filter(created_at__lt=cutoff)
                .delete())
        self.stdout.write(f"Deleted: {d}")