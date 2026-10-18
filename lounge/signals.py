from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile
from .notifications import notify_roles


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        initial_role = UserProfile.Role.ADMIN if instance.is_superuser else UserProfile.Role.USER
        UserProfile.objects.get_or_create(user=instance, defaults={"role": initial_role})
        if not instance.is_superuser:
            notify_roles(
                [UserProfile.Role.ADMIN],
                title="New account registered",
                message=f"{instance.get_username()} created a Ti'Amo's Lounge account.",
                url="/users/",
                category="account",
            )
