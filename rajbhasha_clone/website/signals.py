from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import get_user_model

from .models import UserProfile
from .utils import send_system_email

User = get_user_model()


# 🔹 Create profile automatically when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "employee_code": instance.username,
                "role": getattr(instance, "role", "user"),
            }
        )


# 🔹 Always ensure profile exists and sync role
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    profile, created = UserProfile.objects.get_or_create(
        user=instance,
        defaults={
            "employee_code": instance.username,
            "role": getattr(instance, "role", "user"),
        }
    )

    # Keep profile role synced with user role
    if hasattr(instance, "role"):
        profile.role = instance.role
        profile.save()


# 🔹 Login signal
@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    send_system_email(user, request, "login")
