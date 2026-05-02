from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import get_user_model

from .models import UserProfile, Role
from .utils import send_system_email

User = get_user_model()


# Create profile automatically when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        profile, _ = UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "employee_code": instance.username,
            }
        )
        
        # Assign appropriate roles to profile based on user
        if instance.is_superuser:
            # Superuser gets admin role
            admin_role = Role.objects.get_or_create(name='admin')[0]
            profile.roles.add(admin_role)
        else:
            # Regular users get user role
            user_role = Role.objects.get_or_create(name='user')[0]
            profile.roles.add(user_role)


#  Always ensure profile exists and sync roles
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # 1. Prevent this signal from running when we are just updating the OTP
    update_fields = kwargs.get('update_fields')
    if update_fields and 'otp' in update_fields:
        return

    try:
        profile, created = UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "employee_code": instance.username,
            }
        )

        # Sync user roles with profile roles
        if instance.is_superuser:
            # Superuser should have admin role
            admin_role = Role.objects.get_or_create(name='admin')[0]
            if not instance.roles.filter(name='admin').exists():
                instance.roles.add(admin_role)
            if not profile.roles.filter(name='admin').exists():
                profile.roles.add(admin_role)
        elif not instance.roles.exists():
            # Ensure user has at least 'user' role
            user_role = Role.objects.get_or_create(name='user')[0]
            instance.roles.add(user_role)
            profile.roles.add(user_role)
            
    except Exception as e:
        # Catch IntegrityErrors gracefully if a username overlaps with an existing employee_code
        print(f"Profile auto-create skipped due to conflict: {e}")
        pass


#  Login signal
@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    send_system_email(user, request, "login")
