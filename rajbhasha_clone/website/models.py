from django.db import models
from django.contrib.auth.models import AbstractUser
from cryptography.fernet import Fernet
from django.conf import settings
import hashlib
import json
import datetime
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
        ('hod', 'HOD'),
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
    objects = CustomUserManager()
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

    designation = models.CharField(max_length=100, blank=True, null=True)
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
    encrypted_super_annuation_date = models.BinaryField(null=True, blank=True)
    def __str__(self):
        return f"{self.empcode} - {self.ename}"

    def set_super_annuation_date(self, date_obj):
        """Encrypts a date object and stores it."""
        if date_obj:
            date_str = date_obj.strftime('%Y-%m-%d')
            self.encrypted_super_annuation_date = cipher_suite.encrypt(date_str.encode())
        else:
            self.encrypted_super_annuation_date = None

    def get_super_annuation_date(self):
        if self.encrypted_super_annuation_date:
            decrypted_str = cipher_suite.decrypt(self.encrypted_super_annuation_date).decode()
            return datetime.datetime.strptime(decrypted_str, '%Y-%m-%d').date()
        return None

    @property
    def super_annuation_date(self):
        return self.get_super_annuation_date()

    @super_annuation_date.setter
    def super_annuation_date(self, value):
        self.set_super_annuation_date(value)

class TranslationCache(models.Model):
    source_text = models.TextField()
    target_lang = models.CharField(max_length=10)
    translated_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # This explicitly names the table to match your error
        db_table = 'my_translation_cache'

class UserProfile(models.Model):
    """Extended user profile for storing additional information"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('manager', 'Manager'),
        ('hod', 'HOD'),
        ('admin', 'Admin'),
        ('backup_user', 'Backup User'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    employee_code = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    hod_name = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    office_name = models.CharField(max_length=255, blank=True, null=True)
    office_code = models.CharField(max_length=50, blank=True, null=True)
    profile_updated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.employee_code} - {self.role}"
    
    class Meta:
        ordering = ['-id']


class ManagerRequest(models.Model):
    """Stores requests from HOD to Manager for profile/QPR updates"""
    REQUEST_TYPE_CHOICES = [
        ('profile', 'Profile Update'),
        ('qpr', 'QPR Update'),
        ('both', 'Both Profile and QPR'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    hod = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='manager_requests_sent')
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='manager_requests_received')
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.hod.profile.employee_code} -> {self.user.profile.employee_code}"
    
    class Meta:
        ordering = ['-created_at']


class EditRequest(models.Model):
    """Track edit requests for QPR and Profile data that require admin approval"""
    REQUEST_TYPE_CHOICES = [
        ('profile', 'Profile Update'),
        ('qpr', 'QPR Update'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('used', 'Used'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='edit_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Store the requested changes as JSON
    requested_data = models.JSONField(default=dict)
    
    # Related record IDs
    qpr_record_id = models.IntegerField(null=True, blank=True)  # For QPR edit requests
    
    # Reason/Comments
    reason = models.TextField(blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Approved by admin
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_edit_requests'
    )
    
    def __str__(self):
        return f"{self.user.username} - {self.request_type} ({self.status})"
    
    class Meta:
        ordering = ['-created_at']


class QPRRecord(models.Model):
    """Main QPR Record - stores header information"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='qpr_records',null=True,blank=True)
    officeName = models.CharField(max_length=255)
    officeCode = models.CharField(max_length=50)
    region = models.CharField(max_length=100)
    quarter = models.CharField(max_length=50)
    year = models.CharField(max_length=20, default='2025-2026', null=True, blank=True)
    status = models.CharField(max_length=50, default='Draft')
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_submitted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.officeName} - {self.quarter}"

    class Meta:
        ordering = ['-id']


# ---------- Sections ----------

class Section1FilesData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section1')
    total_files = models.IntegerField(null=True, blank=True)
    hindi_files = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section2MeetingsData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section2')
    meetings_count = models.IntegerField(null=True, blank=True)
    hindi_minutes = models.IntegerField(null=True, blank=True)
    total_papers = models.IntegerField(null=True, blank=True)
    hindi_papers = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section3OfficialLanguagesData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section3')
    total_documents = models.IntegerField(null=True, blank=True)
    bilingual_documents = models.IntegerField(null=True, blank=True)
    english_only_documents = models.IntegerField(null=True, blank=True)
    hindi_only_documents = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section4HindiLettersData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section4')
    total_letters = models.IntegerField(null=True, blank=True)
    no_reply_letters = models.IntegerField(null=True, blank=True)
    replied_hindi_letters = models.IntegerField(null=True, blank=True)
    replied_english_letters = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section5EnglishRepliedHindiData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section5')
    region_a_english_letters = models.IntegerField(null=True, blank=True)
    region_a_replied_hindi = models.IntegerField(null=True, blank=True)
    region_a_replied_english = models.IntegerField(null=True, blank=True)
    region_a_no_reply = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section6IssuedLettersData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section6')
    region_a_hindi_bilingual = models.IntegerField(null=True, blank=True)
    region_a_english_only = models.IntegerField(null=True, blank=True)
    region_a_total = models.IntegerField(null=True, blank=True)
    region_b_hindi_bilingual = models.IntegerField(null=True, blank=True)
    region_b_english_only = models.IntegerField(null=True, blank=True)
    region_b_total = models.IntegerField(null=True, blank=True)
    region_c_hindi_bilingual = models.IntegerField(null=True, blank=True)
    region_c_english_only = models.IntegerField(null=True, blank=True)
    region_c_total = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section7NotingsData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section7')
    hindi_pages = models.IntegerField(null=True, blank=True)
    english_pages = models.IntegerField(null=True, blank=True)
    total_pages = models.IntegerField(null=True, blank=True)
    eoffice_notings = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section8WorkshopsData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section8')
    full_day_workshops = models.IntegerField(null=True, blank=True)
    officers_trained = models.IntegerField(null=True, blank=True)
    employees_trained = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section9ImplementationCommitteeData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section9')
    meeting_date = models.DateField(null=True, blank=True)
    sub_committees_count = models.IntegerField(null=True, blank=True)
    meetings_organized = models.IntegerField(null=True, blank=True)
    agenda_hindi = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section10HindiAdvisoryData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section10')
    meeting_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Section11SpecificAchievementsData(models.Model):
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='section11')
    innovative_work = models.TextField(blank=True, null=True)
    special_events = models.TextField(blank=True, null=True)
    hindi_medium_works = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TypingUsageReport(models.Model):
    """Store typing usage report data for users"""
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='typing_usage_report')
    total_words = models.IntegerField(null=True, blank=True)
    hindi_words = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Typing Usage Report - {self.qpr_record.officeName}"

    class Meta:
        ordering = ['-created_at']
