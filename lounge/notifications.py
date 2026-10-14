from django.contrib.auth import get_user_model
from .models import Notification, UserProfile


User = get_user_model()


def notify_users(users, *, title, message, url="", category="activity", actor=None):
    recipient_ids = {user.pk for user in users if user and user.is_active}
    Notification.objects.bulk_create([
        Notification(
            recipient_id=user_id,
            actor=actor if getattr(actor, "pk", None) else None,
            category=category,
            title=title,
            message=message,
            url=url,
        )
        for user_id in recipient_ids
    ])


def notify_roles(roles, *, title, message, url="", category="activity", actor=None):
    users = User.objects.filter(
        is_active=True,
        profile__role__in=roles,
    ).distinct()
    if getattr(actor, "pk", None):
        users = users.exclude(pk=actor.pk)
    notify_users(users, title=title, message=message, url=url, category=category, actor=actor)


def notify_email_account(email, *, title, message, url="", category="activity", actor=None):
    users = User.objects.filter(is_active=True, email__iexact=email)
    notify_users(users, title=title, message=message, url=url, category=category, actor=actor)
