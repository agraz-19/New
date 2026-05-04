from __future__ import annotations

from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager, User
from cryptography.fernet import Fernet
from django.conf import settings
import hashlib
import json
import datetime
from django.contrib.auth.models import BaseUserManager

cipher_suite = Fernet(settings.ENCRYPTION_KEY)

class Role(models.Model):
    """Role model for multi-role support"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('manager', 'Manager'),
        ('hod', 'HOD'),
        ('admin', 'Admin'),
        ('backup_user', 'Backup User'),
    ]
    name = models.CharField(max_length=20, unique=True, choices=ROLE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class CustomUserManager(UserManager["CustomUser"]):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        # Use your custom encryption method
        user.set_email(email) 
        user.save(using=self._db)
        # Assign 'user' role by default
        user_role = Role.objects.get_or_create(name='user')[0]
        user.roles.add(user_role)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        user = self.create_user(username, email, password, **extra_fields)
        # Assign 'admin' role
        admin_role = Role.objects.get_or_create(name='admin')[0]
        user.roles.add(admin_role)
        return user

class CustomUser(AbstractUser):
    email_hash = models.CharField(max_length=64, unique=False, null=True, blank=True)
    encrypted_email_data = models.BinaryField(null=True, blank=True)
    email = models.EmailField(unique=False, null=True, blank=True)
    roles = models.ManyToManyField(Role, related_name='users', blank=True)
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
            return cipher_suite.decrypt(bytes(self.encrypted_email_data)).decode()
        return None
    @property
    def role(self):
        """Return primary role string for template compatibility (admin > manager > hod > user > backup_user)."""
        try:
            priority_roles = ['admin', 'manager', 'hod', 'user', 'backup_user']
            for r in priority_roles:
                if self.roles.filter(name=r).exists():
                    return r
        except Exception:
            return None
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


class Office(models.Model):
    """Office lookup table created by admin via Quick Actions"""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Employee(models.Model):
    empcode = models.IntegerField(unique=True)
    
    ename = models.CharField(null=True, blank=True) 
    hname = models.CharField(max_length=255)
    DESIGNATION_CHOICES = [
        ("Scientist-G", "Scientist-G"),
        ("Scientist-F", "Scientist-F"),
        ("Scientist-E", "Scientist-E"),
        ("Scientist-D", "Scientist-D"),
        ("Scientist-C", "Scientist-C"),
        ("Scientist-B", "Scientist-B"),
        ("Section Officer", "Section Officer"),
        ("Senior Secretariate Assistant", "Senior Secretariate Assistant"),
        ("Scientific/Technical Assistant-A", "Scientific/Technical Assistant-A"),
        ("Scientific/Technical Assistant-B", "Scientific/Technical Assistant-B"),
        ("Scientific Officer/Engineer-SB", "Scientific Officer/Engineer-SB"),
    ]

    designation = models.CharField(
        max_length=100,
        choices=DESIGNATION_CHOICES,
        blank=True,
        null=True
    )
    GAZET_CHOICES = [
        ("Gazetted", "Gazetted"),
        ("Non-Gazetted", "Non-Gazetted"),
    ]
    gazet = models.CharField(max_length=50, choices=GAZET_CHOICES)
    YES_NO_CHOICES = [
        ("Yes", "Yes"),
        ("No", "No"),
    ]
    stenographer = models.CharField(
        max_length=5,
        choices=YES_NO_CHOICES,
        blank=True,
        null=True
    )
    Hindiexam_choices=[
            ("Prabodh", "Prabodh"),
            ("Praveen", "Praveen"),
            ("Pragya", "Pragya"),
            ("Parangat", "Parangat")
        ]

    highest_exam = models.CharField(
        max_length=100,choices=Hindiexam_choices,blank=True,null=True)

    TYPING_CHOICES = [
        ("Hindi", "Hindi"),
        ("English", "English"),
        ("Both", "Both"),
    ]
    typing = models.CharField(max_length=30, choices=TYPING_CHOICES)

    hindiproficiency = models.CharField(
        max_length=5,
        choices=YES_NO_CHOICES,
        blank=True,
        null=True)
    OLIC_AFFILIATE_CHOICES = [
        ('President', 'President'),
        ('Member Secretary', 'Member Secretary'),
        ('Member', 'Member'),
        ('Not Applicable', 'Not Applicable'),
    ]

    olic_affiliate = models.CharField(
        max_length=50,
        choices=OLIC_AFFILIATE_CHOICES,
        blank=True,
        null=True
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
            decrypted_str = cipher_suite.decrypt(bytes(self.encrypted_super_annuation_date)).decode()
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
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    employee_code = models.CharField(max_length=50, unique=True)
    employee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profiles')
    roles = models.ManyToManyField(Role, related_name='user_profiles', blank=True)
    hod_name = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    encrypted_email = models.BinaryField(blank=True, null=True)
    encrypted_phone = models.BinaryField(blank=True, null=True)
    alternate_email = models.EmailField(blank=True, null=True)
    ip_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Auto-filled from employee database"
    )
    
    # Office Information
    office_state = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Auto-filled from employee database"
    )
    office_name = models.CharField(max_length=255, blank=True, null=True)
    office_code = models.CharField(max_length=50, blank=True, null=True)
    # Language region selection used by QPR (e.g., "भाषा क्षेत्र 'क' / Region A")
    language_region = models.CharField(max_length=100, blank=True, null=True)
    profile_updated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending HOD Approval'),
        ('pending_admin','Pending Admin Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    approval_status = models.CharField(
    max_length=20, 
    choices=APPROVAL_STATUS_CHOICES, 
    default='pending'  
    )
    profile_locked = models.BooleanField(default=False)
    @property
    def email(self):
        if self.encrypted_email:
            return cipher_suite.decrypt(bytes(self.encrypted_email)).decode()
        return ""

    @email.setter
    def email(self, value):
        if value:
            self.encrypted_email = cipher_suite.encrypt(value.encode())
        else:
            self.encrypted_email = None

    @property
    def phone(self):
        if self.encrypted_phone:
            return cipher_suite.decrypt(bytes(self.encrypted_phone)).decode()
        return ""

    @phone.setter
    def phone(self, value):
        if value:
            self.encrypted_phone = cipher_suite.encrypt(value.encode())
        else:
            self.encrypted_phone = None
    
    def __str__(self):
        roles_str = ', '.join(self.roles.values_list('name', flat=True))
        return f"{self.employee_code} - {roles_str or 'user'}"
    
    class Meta:
        ordering = ['-id']
        
class ProfileChangeRequest(models.Model):
    """New model to store change requests from employees"""
    REQUEST_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='change_requests')
    # Link to the HOD (CustomUser)
    hod = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='pending_profile_changes')
    change_reason = models.TextField() 
    requested_fields = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_comments = models.TextField(blank=True)
    
    def __str__(self):
        return f"Change Request - {self.profile.user.username} ({self.status})"

    @property
    def requested_field_labels(self):
        labels = {
            'alternate_email': 'Alternate Email',
            'designation': 'Designation',
            'highest_exam': 'Highest Hindi Exam',
        }
        return [labels.get(field, field) for field in self.requested_fields or []]


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
        ('temp use', 'Temp Use'),
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
    region_choices = [
    ("Region A", "भाषा क्षेत्र 'क' / Region A"),
    ("Region B", "भाषा क्षेत्र 'ख' / Region B"),
    ("Region C", "भाषा क्षेत्र 'ग' / Region C"),]
    region = models.CharField(max_length=50,choices=region_choices,blank=True,null=True)
    quarter = models.CharField(max_length=50)
    year = models.CharField(max_length=20, default='2025-2026', null=True, blank=True)
    # Submission frequency: daily/weekly/monthly/quarterly
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='quarterly')
    # Optional explicit period (useful for daily/weekly/monthly submissions)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default='Draft')
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_submitted = models.BooleanField(default=False)
    is_editing_allowed = models.BooleanField(default=False, help_text='Allow editing of submitted form after unlock')
    is_quarterly_frozen = models.BooleanField(default=False, help_text='Freeze quarterly report on quarter end (HOD can freeze only at quarter end)')
    cert_edit_count = models.IntegerField(default=0, help_text='Track certificate edits (max 2)')
    cert_office_code = models.CharField(max_length=50, blank=True, null=True, help_text='Override office code for certificate')
    cert_quarter = models.CharField(max_length=50, blank=True, null=True, help_text='Override quarter for certificate')
    cert_year = models.CharField(max_length=20, blank=True, null=True, help_text='Override year for certificate')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.officeName} - {self.quarter}"

    class Meta:
        ordering = ['-id']

class FinancialYear(models.Model):
    start_year = models.IntegerField()
    end_year = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.start_year}-{self.end_year}"

    class Meta:
        ordering = ['start_year']
        unique_together = ('start_year', 'end_year')


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
    
class CertificateData(models.Model):
    """Store certificate data (year and quarter) selected by manager for each QPR submission"""
    qpr_record = models.OneToOneField(QPRRecord, on_delete=models.CASCADE, related_name='certificate_data')
    financial_year = models.CharField(max_length=20)
    quarter_ending = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate - {self.qpr_record.officeName} ({self.quarter_ending})"

    class Meta:
        ordering = ['-created_at']
class QPRPartTwo(models.Model):
    qpr_record = models.OneToOneField(
        QPRRecord,
        on_delete=models.CASCADE,
        related_name='part2',
        null=True,
        blank=True,
        help_text='Optional link to the main QPRRecord when created from manager UI'
    )
    
    # Tracking user and quarter for "one per quarter" constraint
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='part2_submissions', null=True, blank=True)
    quarter = models.CharField(max_length=20, null=True, blank=True)  # Q1, Q2, Q3, Q4
    year = models.CharField(max_length=20, null=True, blank=True)  # 2024-25
    
    financial_year = models.CharField(max_length=20, help_text="e.g., 2023-24") # [cite: 124]
    
    # --- Section 1: Rule 10(4) Notification ---
    is_notified_rule_10_4 = models.BooleanField(
        default=False, 
        verbose_name="Notified under Rule 10(4)"
    ) # [cite: 70, 71]
    total_sub_offices = models.PositiveIntegerField(default=0) # [cite: 72, 73]
    notified_sub_offices = models.PositiveIntegerField(default=0) # [cite: 73]

    # --- Section 3: Computer Training ---
    computer_training_total_staff = models.PositiveIntegerField(default=0) # [cite: 80, 81]
    computer_training_trained = models.PositiveIntegerField(default=0) # [cite: 81]
    computer_training_working = models.PositiveIntegerField(default=0) # [cite: 81]

    # --- Section 4: Computers/Laptops ---
    total_computers = models.PositiveIntegerField(default=0) # [cite: 82, 83]
    hindi_enabled_computers = models.PositiveIntegerField(default=0) # [cite: 83]
    hindi_work_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # --- Section 6: Rule 8(4) Individual Orders ---
    officials_issued_rule_8_4_orders = models.PositiveIntegerField(default=0) # [cite: 86]

    # --- Section 7: Training Programme (For Training Institutes) ---
    training_total_duration_hours = models.PositiveIntegerField(default=0) # [cite: 87, 88]
    training_imparted_hindi = models.PositiveIntegerField(default=0) # [cite: 88]
    training_imparted_english = models.PositiveIntegerField(default=0) # [cite: 88]
    training_imparted_mixed = models.PositiveIntegerField(default=0) # [cite: 88]

    # --- Section 8: Inspections ---
    sec8_total_sections = models.PositiveIntegerField(default=0) # [cite: 89, 91]
    sec8_inspected_sections = models.PositiveIntegerField(default=0) # [cite: 92]
    sec8_total_sub_offices = models.PositiveIntegerField(default=0) # [cite: 93]
    sec8_inspected_sub_offices = models.PositiveIntegerField(default=0) # [cite: 94]

    # --- Section 9: Magazines Publication ---
    magazines_total = models.PositiveIntegerField(default=0) # [cite: 95, 96]
    magazines_hindi = models.PositiveIntegerField(default=0) # [cite: 96]
    magazines_english = models.PositiveIntegerField(default=0) # [cite: 96]

    # --- Section 10: Hindi Books Purchase ---
    expenditure_total_books = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) # [cite: 97, 98]
    expenditure_hindi_books = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) # [cite: 99]

    # --- Section 15: Other Achievements ---
    hindi_event_start_date = models.DateField(null=True, blank=True) # [cite: 111, 112]
    hindi_event_end_date = models.DateField(null=True, blank=True) # [cite: 112, 114]
    seminar_date = models.DateField(null=True, blank=True) # [cite: 113]
    seminar_subject = models.CharField(max_length=255, blank=True) # [cite: 113]
    other_activities_date = models.DateField(null=True, blank=True) # [cite: 115]
    other_activities_subject = models.CharField(max_length=255, blank=True) # [cite: 115]

    # Submission tracking
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='submitted_part2')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    
    # --- Section 16: Certificate Contact Info ---
    chairperson_name = models.CharField(max_length=255, blank=True, null=True)
    chairperson_designation = models.CharField(max_length=255, blank=True, null=True)
    chairperson_phone = models.CharField(max_length=50, blank=True, null=True)
    chairperson_fax = models.CharField(max_length=50, blank=True, null=True)
    chairperson_email = models.EmailField(blank=True, null=True)

    def __str__(self):
        if self.user and self.quarter:
            return f"Certificate Part II - {self.user.profile.employee_id} ({self.quarter})"
        return f"QPR Part II - {self.financial_year}"

    class Meta:
        # Ensure one certificate per quarter per user
        unique_together = (('user', 'quarter', 'year'), )


class ManagerQPR(models.Model):
    """Quarterly snapshot QPR for Managers - non-cumulative, one submission per user per quarter"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='manager_qprs')
    financial_year = models.CharField(max_length=20)
    quarter = models.CharField(max_length=50)

    # Base numeric sections (2,4,5,6,7)
    # Section 2: meetings/files at Secretary level
    s2_meetings_count = models.IntegerField(null=True, blank=True)
    s2_hindi_minutes = models.IntegerField(null=True, blank=True)
    s2_total_papers = models.IntegerField(null=True, blank=True)
    s2_hindi_papers = models.IntegerField(null=True, blank=True)

    # Section 4: Hindi letters received
    s4_total_letters = models.IntegerField(null=True, blank=True)
    s4_no_reply_letters = models.IntegerField(null=True, blank=True)
    s4_replied_hindi_letters = models.IntegerField(null=True, blank=True)
    s4_replied_english_letters = models.IntegerField(null=True, blank=True)

    # Section 5: English replied in Hindi (region A example fields)
    s5_region_a_english_letters = models.IntegerField(null=True, blank=True)
    s5_region_a_replied_hindi = models.IntegerField(null=True, blank=True)
    s5_region_a_replied_english = models.IntegerField(null=True, blank=True)
    s5_region_a_no_reply = models.IntegerField(null=True, blank=True)

    # Section 6: Issued letters (per region totals)
    s6_region_a_hindi_bilingual = models.IntegerField(null=True, blank=True)
    s6_region_a_english_only = models.IntegerField(null=True, blank=True)
    s6_region_a_total = models.IntegerField(null=True, blank=True)
    s6_region_b_hindi_bilingual = models.IntegerField(null=True, blank=True)
    s6_region_b_english_only = models.IntegerField(null=True, blank=True)
    s6_region_b_total = models.IntegerField(null=True, blank=True)
    s6_region_c_hindi_bilingual = models.IntegerField(null=True, blank=True)
    s6_region_c_english_only = models.IntegerField(null=True, blank=True)
    s6_region_c_total = models.IntegerField(null=True, blank=True)

    # Section 7: Notings
    s7_hindi_pages = models.IntegerField(null=True, blank=True)
    s7_english_pages = models.IntegerField(null=True, blank=True)
    s7_total_pages = models.IntegerField(null=True, blank=True)
    s7_eoffice_notings = models.IntegerField(null=True, blank=True)

    # Section 8: Workshops
    s8_full_day_workshops = models.IntegerField(null=True, blank=True)
    s8_officers_trained = models.IntegerField(null=True, blank=True)
    s8_employees_trained = models.IntegerField(null=True, blank=True)

    # Section 9: Implementation committee
    s9_meeting_date = models.DateField(null=True, blank=True)
    s9_sub_committees_count = models.IntegerField(null=True, blank=True)
    s9_meetings_organized = models.IntegerField(null=True, blank=True)
    s9_agenda_hindi = models.CharField(max_length=10, null=True, blank=True)

    # Section 10: Hindi advisory committee meeting date
    s10_meeting_date = models.DateField(null=True, blank=True)

    # Section 11: Specific achievements
    s11_innovative_work = models.TextField(null=True, blank=True)
    s11_special_events = models.TextField(null=True, blank=True)
    s11_hindi_medium_works = models.TextField(null=True, blank=True)

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Manager QPR - {self.user.username} ({self.quarter})"

    class Meta:
        unique_together = (('user', 'quarter'),)
        ordering = ['-created_at']


class AdminQPR(models.Model):
    """Quarterly snapshot QPR for Admins - non-cumulative, one submission per user per quarter"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_qprs')
    financial_year = models.CharField(max_length=20)
    quarter = models.CharField(max_length=50)

    # Section 2 fields for AdminQPR
    a_s2_meetings_count = models.IntegerField(null=True, blank=True)
    a_s2_hindi_minutes = models.IntegerField(null=True, blank=True)
    a_s2_total_papers = models.IntegerField(null=True, blank=True)
    a_s2_hindi_papers = models.IntegerField(null=True, blank=True)

    # Section 3: Official languages documents
    a_s3_total_documents = models.IntegerField(null=True, blank=True)
    a_s3_bilingual_documents = models.IntegerField(null=True, blank=True)
    a_s3_english_only_documents = models.IntegerField(null=True, blank=True)
    a_s3_hindi_only_documents = models.IntegerField(null=True, blank=True)

    # Section 4 fields
    a_s4_total_letters = models.IntegerField(null=True, blank=True)
    a_s4_no_reply_letters = models.IntegerField(null=True, blank=True)
    a_s4_replied_hindi_letters = models.IntegerField(null=True, blank=True)
    a_s4_replied_english_letters = models.IntegerField(null=True, blank=True)

    # Section 5
    a_s5_region_a_english_letters = models.IntegerField(null=True, blank=True)
    a_s5_region_a_replied_hindi = models.IntegerField(null=True, blank=True)
    a_s5_region_a_replied_english = models.IntegerField(null=True, blank=True)
    a_s5_region_a_no_reply = models.IntegerField(null=True, blank=True)

    # Section 6 (issued letters)
    a_s6_region_a_hindi_bilingual = models.IntegerField(null=True, blank=True)
    a_s6_region_a_english_only = models.IntegerField(null=True, blank=True)
    a_s6_region_a_total = models.IntegerField(null=True, blank=True)
    a_s6_region_b_hindi_bilingual = models.IntegerField(null=True, blank=True)
    a_s6_region_b_english_only = models.IntegerField(null=True, blank=True)
    a_s6_region_b_total = models.IntegerField(null=True, blank=True)
    a_s6_region_c_hindi_bilingual = models.IntegerField(null=True, blank=True)
    a_s6_region_c_english_only = models.IntegerField(null=True, blank=True)
    a_s6_region_c_total = models.IntegerField(null=True, blank=True)

    # Section 7 (notings)
    a_s7_hindi_pages = models.IntegerField(null=True, blank=True)
    a_s7_english_pages = models.IntegerField(null=True, blank=True)
    a_s7_total_pages = models.IntegerField(null=True, blank=True)
    a_s7_eoffice_notings = models.IntegerField(null=True, blank=True)

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Admin QPR - {self.user.username} ({self.quarter})"

    class Meta:
        unique_together = (('user', 'quarter'),)
        ordering = ['-created_at']
    
class StaffHindiKnowledge(models.Model):
    report = models.ForeignKey(
        QPRPartTwo,
        on_delete=models.CASCADE,
        related_name='staff_knowledge'
    )

    CATEGORY_CHOICES = [
        ('total', 'Total'),
        ('secretarial', 'Secretarial'),
        ('knowledge', 'Knowledge of Hindi'),
        ('being_trained', 'Being trained'),
        ('yet_to_be_trained', 'Yet to be trained'),
    ]

    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)

    # For (a), (b), (d), (e)
    officers_total = models.PositiveIntegerField(default=0)
    employees_total = models.PositiveIntegerField(default=0)

    # ONLY for (c)
    officers_working = models.PositiveIntegerField(default=0)
    officers_proficient = models.PositiveIntegerField(default=0)

    employees_working = models.PositiveIntegerField(default=0)
    employees_proficient = models.PositiveIntegerField(default=0)

    total_count = models.PositiveIntegerField(default=0)

class TypingStenographyKnowledge(models.Model):
    """Section 2(ii): Knowledge of Hindi Stenography/Typing""" # [cite: 76]
    CATEGORY_CHOICES = [
        ('stenographer', 'Stenographer'), # [cite: 77]
        ('typist_clerk', 'Typists/Clerks/Assistant Section Officer'), # [cite: 77]
        ('tax_postal', 'Tax/Postal Asstt. etc.') # [cite: 77]
    ]
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='typing_knowledge')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    total_no = models.PositiveIntegerField(default=0) # [cite: 77]
    trained_in_hindi = models.PositiveIntegerField(default=0) # [cite: 77]
    work_in_hindi = models.PositiveIntegerField(default=0) # [cite: 77]
    yet_to_be_trained = models.PositiveIntegerField(default=0) # [cite: 77]

class TranslationKnowledge(models.Model):
    """Section 2(iii): Knowledge of Translation""" # [cite: 78]
    CATEGORY_CHOICES = [
        ('engaged', 'Engaged in Translation Work'), # [cite: 79]
        ('trained', 'Got training in Translation'), # [cite: 79]
        ('yet_to_be_trained', 'Yet to be trained') # [cite: 79]
    ]
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='translation_knowledge')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    officers_count = models.PositiveIntegerField(default=0) # [cite: 79]
    employees_count = models.PositiveIntegerField(default=0) # [cite: 79]
    total_count = models.PositiveIntegerField(default=0)

class CodeManualStandardForms(models.Model):
    """Section 5: Code, Manual, Standard Forms etc.""" # [cite: 84]
    CATEGORY_CHOICES = [
        ('acts_rules', 'Acts/Rules/Official codes/Manuals/Procedural literature etc.'), # [cite: 85]
        ('standard_forms', 'Standard Forms') # [cite: 85]
    ]
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='codes_manuals')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    total_no = models.PositiveIntegerField(default=0) # [cite: 85]
    bilingual_no = models.PositiveIntegerField(default=0) # [cite: 85]

class OfficersWorkInHindi(models.Model):
    """Section 11 & 12: Work done by officers""" # [cite: 100, 102, 103]
    LEVEL_CHOICES = [
        ('ds_and_above', 'Deputy Secretary/Equivalent and above'), # [cite: 100]
        ('below_ds', 'Below the level of Deputy Secretary/Equivalent') # [cite: 103]
    ]
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='officers_work')
    level = models.CharField(max_length=50, choices=LEVEL_CHOICES)
    total_officers = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    knowledge_of_hindi = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    not_doing = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    doing_upto_25 = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    doing_26_to_50 = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    doing_51_to_75 = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    doing_more_76 = models.PositiveIntegerField(default=0) # [cite: 101, 104]
    doing_cent_percent = models.PositiveIntegerField(default=0) # [cite: 101, 104]

class HindiPost(models.Model):
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='hindi_posts')

    designation = models.CharField(max_length=255)

    # Headquarters
    hq_sanctioned = models.PositiveIntegerField(default=0)
    hq_vacant = models.PositiveIntegerField(default=0)

    # Subordinate offices
    sub_sanctioned = models.PositiveIntegerField(default=0)
    sub_vacant = models.PositiveIntegerField(default=0)
    
class WebsiteDetail(models.Model):
    """Section 14: Website""" # [cite: 107]
    STATUS_CHOICES = [
        ('english_only', 'Only in English'), # [cite: 110]
        ('partially_bilingual', 'Partially Bilingual'), # [cite: 110]
        ('fully_bilingual', 'Fully Bilingual') # [cite: 110]
    ]
    report = models.ForeignKey(QPRPartTwo, on_delete=models.CASCADE, related_name='websites')
    url = models.URLField(verbose_name="Address of Website") # [cite: 110]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES) # [cite: 110]


class QPRFinalization(models.Model):
    """Track when users finalize their QPR for a given quarter"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='qpr_finalizations')
    quarter = models.CharField(max_length=50)
    year = models.CharField(max_length=20)
    finalized_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'quarter', 'year')
        ordering = ['-finalized_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.quarter} {self.year}"

