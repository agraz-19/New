from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .utils import send_system_email

@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    send_system_email(user, request, 'login')