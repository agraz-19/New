from django.db import models
from django.conf import settings


class UserProfile(models.Model):
    """Extended user profile for storing additional information"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('hod', 'HOD'),
        ('admin', 'Admin/Manager'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    employee_code = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
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
