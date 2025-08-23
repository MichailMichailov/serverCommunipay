# apiCommuniPay/common/access.py
from django.db.models import Q
from django.utils.timezone import now
from apiCommuniPay.clubs.models import Subscription

def user_has_chat_access(user, chat) -> bool:
    qs = Subscription.objects.filter(
        user=user,
        status='active',
        plan__project=chat.project,
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now())
    )
    return qs.filter(Q(plan__all_channels=True) | Q(plan__channels=chat)).exists()
