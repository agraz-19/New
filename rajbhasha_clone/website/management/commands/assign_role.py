"""
Management command to assign roles to users
Usage: python manage.py assign_role <username> <role_name> [--remove]
Example: python manage.py assign_role emp123 hod
Example: python manage.py assign_role emp123 manager --remove
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from website.models import Role

User = get_user_model()


class Command(BaseCommand):
    help = 'Assign or remove roles to/from users'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username of the user')
        parser.add_argument('role', type=str, help='Role name (user, manager, hod, admin, backup_user)')
        parser.add_argument('--remove', action='store_true', help='Remove the role instead of adding it')

    def handle(self, *args, **options):
        username = options['username']
        role_name = options['role']
        remove = options['remove']

        # Validate role name
        valid_roles = ['user', 'manager', 'hod', 'admin', 'backup_user']
        if role_name not in valid_roles:
            raise CommandError(f"Invalid role '{role_name}'. Valid roles: {', '.join(valid_roles)}")

        # Get the user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")

        # Get the role
        try:
            role = Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            raise CommandError(f"Role '{role_name}' not found")

        if remove:
            # Remove the role
            user.roles.remove(role)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Removed role '{role_name}' from user '{username}'")
            )
        else:
            # Add the role
            user.roles.add(role)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Added role '{role_name}' to user '{username}'")
            )

        # Show current roles
        current_roles = list(user.roles.values_list('name', flat=True))
        self.stdout.write(f"  Current roles: {', '.join(current_roles) or 'none'}")
