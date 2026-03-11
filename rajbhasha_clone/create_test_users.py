import os
import django
import sys

# Setup Django environment
sys.path.append('/Users/preethamtirupati/user_registration/root/rajbhasha_clone')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from website.models import CustomUser, UserProfile, Role

def create_test_user(username, email, role_name, password='password123'):
    user, created = CustomUser.objects.get_or_create(username=username)
    if created:
        print(f"Creating user {username}...")
        user.set_password(password)
        user.set_email(email)
        if role_name == 'admin':
            user.is_superuser = True
            user.is_staff = True
        user.save()
        
        # Assign roles
        role = Role.objects.get(name=role_name)
        user.roles.add(role)
        
        # Create or update profile
        profile, p_created = UserProfile.objects.get_or_create(user=user, defaults={'employee_code': f'EMP_{username.upper()}'})
        profile.roles.add(role)
        profile.name = f"{username.title()} User"
        profile.employee_code = f'EMP_{username.upper()}'
        profile.save()
        
        print(f"Created {role_name} user: {username} / {password}")
    else:
        # Ensure password and roles are set correctly even if user exists
        user.set_password(password)
        if role_name == 'admin':
            user.is_superuser = True
            user.is_staff = True
        user.save()
        
        # Update roles
        user.roles.clear()
        role = Role.objects.get(name=role_name)
        user.roles.add(role)
        
        profile, p_created = UserProfile.objects.get_or_create(user=user, defaults={'employee_code': f'EMP_{username.upper()}'})
        profile.roles.clear()
        profile.roles.add(role)
        profile.save()
        print(f"Updated {role_name} user: {username} / {password}")

if __name__ == '__main__':
    print("--- Creating Test Users ---")
    create_test_user('admin_test', 'admin@example.com', 'admin')
    create_test_user('hod_test', 'hod@example.com', 'hod')
    create_test_user('manager_test', 'manager@example.com', 'manager')
    create_test_user('user_test', 'user@example.com', 'user')
    print("--- Done ---")
