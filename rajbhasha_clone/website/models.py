from django.db import models
from django.contrib.auth.models import AbstractUser
from cryptography.fernet import Fernet
from django.conf import settings
import hashlib
import json
from django.contrib.auth.models import BaseUserManager

cipher_suite = Fernet(settings.ENCRYPTION_KEY)

class CustomUserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        # Use your custom encryption method
        user.set_email(email) 
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(username, email, password, **extra_fields)

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
        ('backup_user', 'Backup User'),
    ]
    email_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    encrypted_email_data = models.BinaryField(null=True, blank=True)
    email = models.EmailField(unique=False, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    consent_given_at = models.DateTimeField(null=True, blank=True)
    
    is_frozen = models.BooleanField(default=False)
    is_edit_allowed = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    objects = CustomUserManager() # Attach the new manager
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    def __init__(self, *args, **kwargs):
        email_str = kwargs.pop('email', None)
        super().__init__(*args, **kwargs)
        if email_str:
            self.set_email(email_str)
    def set_email(self, email_str):
        email_str = email_str.lower().strip()
        self.email_hash = hashlib.sha256(email_str.encode()).hexdigest()
        self.encrypted_email_data = cipher_suite.encrypt(email_str.encode())
        self.email = ""

    def get_email(self):
        if self.encrypted_email_data:
            return cipher_suite.decrypt(self.encrypted_email_data).decode()
        return None
class DataAccessLog(models.Model):
    accessed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='audit_actions')
    target_user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='access_history')
    access_time = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.accessed_by.username} accessed {self.target_user.username} at {self.access_time}"

class ArchivedUser(models.Model):
    # Store encrypted PII for long-term retention
    username = models.CharField(max_length=150)
    email_hash = models.CharField(max_length=64)
    encrypted_email_data = models.BinaryField()
    employee_snapshot = models.TextField(null=True, blank=True) 
    archived_at = models.DateTimeField(auto_now_add=True)
    original_user_id = models.IntegerField()


class Employee(models.Model):
    empcode = models.IntegerField(unique=True)
    
    ename = models.CharField(null=True, blank=True) 
    hname = models.CharField(max_length=255)

    designation = models.CharField(max_length=100)

    GAZET_CHOICES = [
        ("Gazetted", "Gazetted"),
        ("Non-Gazetted", "Non-Gazetted"),
    ]
    gazet = models.CharField(max_length=50, choices=GAZET_CHOICES)

    EXAM_STATUS = [
        ("Passed", "Passed"),
        ("Failed", "Failed"),
        ("Did not Appear", "Did not Appear"),
    ]
    prabodh = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    praveen = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    pragya = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    parangat = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)

    TYPING_CHOICES = [
        ("Hindi", "Hindi"),
        ("English", "English"),
        ("Both", "Both"),
    ]
    typing = models.CharField(max_length=30, choices=TYPING_CHOICES)

    HINDI_PROFICIENCY_CHOICES = [
        ("Good", "Good"),
        ("Average", "Average"),
        ("Basic", "Basic"),
    ]
    hindiproficiency = models.CharField(
        max_length=30, choices=HINDI_PROFICIENCY_CHOICES
    )

    status = models.CharField(
        max_length=10,
        choices=[("draft", "Draft"), ("submitted", "Submitted")],
        default="draft",
    )

    lastupdate = models.DateTimeField("Last Updated On", auto_now=True)
    super_annuation_date = models.DateField(
        "Superannuation Date", null=True, blank=True
    )

    def __str__(self):
        return f"{self.empcode} - {self.ename}"
