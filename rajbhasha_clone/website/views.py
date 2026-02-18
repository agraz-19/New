import os,io,csv,random,hashlib,json
from datetime import datetime
from django.utils.timezone import now
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout, get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from django.core.cache import cache
from django.urls import reverse
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from gtts import gTTS
from captcha.models import CaptchaStore
from deep_translator import GoogleTranslator
from .models import (
    Employee, CustomUser, DataAccessLog, ArchivedUser, cipher_suite,
    QPRRecord, Section1FilesData, Section2MeetingsData,
    Section3OfficialLanguagesData, Section4HindiLettersData,
    Section5EnglishRepliedHindiData, Section6IssuedLettersData,
    Section7NotingsData, Section8WorkshopsData,
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData,
    Section11SpecificAchievementsData, UserProfile, ManagerRequest
)
from .forms import CustomLoginForm, CustomUserCreationForm
from .employeeform import EmployeeForm
from .serializers import EmployeeSerializer
from .utils import send_system_email
from .templatetags.translate_tags import translate_text

User = get_user_model()

def is_admin(user):
    return user.is_authenticated and user.role == 'admin'

def _convert_to_int(value):
    if value == '' or value is None: return None
    try: return int(value)
    except (ValueError, TypeError): return None

def _convert_to_date(value):
    if value == '' or value is None: return None
    try:
        if isinstance(value, str): return datetime.fromisoformat(value).date()
        return value
    except (ValueError, TypeError, AttributeError): return None

def _save_section_data(record, details):
    # Section 1
    s1, _ = Section1FilesData.objects.get_or_create(qpr_record=record)
    s1.total_files = _convert_to_int(details.get('s1_total'))
    s1.hindi_files = _convert_to_int(details.get('s1_hindi'))
    s1.save()
    # Section 2
    s2, _ = Section2MeetingsData.objects.get_or_create(qpr_record=record)
    s2.meetings_count = _convert_to_int(details.get('s2_meetings'))
    s2.hindi_minutes = _convert_to_int(details.get('s2_minutes'))
    s2.total_papers = _convert_to_int(details.get('s2_papers_total'))
    s2.hindi_papers = _convert_to_int(details.get('s2_papers_hindi'))
    s2.save()
    # Section 3
    s3, _ = Section3OfficialLanguagesData.objects.get_or_create(qpr_record=record)
    s3.total_documents = _convert_to_int(details.get('s3_total'))
    s3.bilingual_documents = _convert_to_int(details.get('s3_bilingual'))
    s3.english_only_documents = _convert_to_int(details.get('s3_english'))
    s3.hindi_only_documents = _convert_to_int(details.get('s3_hindi_only'))
    s3.save()
    # Section 4
    s4, _ = Section4HindiLettersData.objects.get_or_create(qpr_record=record)
    s4.total_letters = _convert_to_int(details.get('s4_total'))
    s4.no_reply_letters = _convert_to_int(details.get('s4_no_reply'))
    s4.replied_hindi_letters = _convert_to_int(details.get('s4_replied_hindi'))
    s4.replied_english_letters = _convert_to_int(details.get('s4_replied_eng'))
    s4.save()
    # Section 5
    s5, _ = Section5EnglishRepliedHindiData.objects.get_or_create(qpr_record=record)
    s5.region_a_english_letters = _convert_to_int(details.get('s5_total'))
    s5.region_a_replied_hindi = _convert_to_int(details.get('s5_hindi'))
    s5.region_a_replied_english = _convert_to_int(details.get('s5_english'))
    s5.region_a_no_reply = _convert_to_int(details.get('s5_noreply'))
    s5.save()
    # Section 6
    s6, _ = Section6IssuedLettersData.objects.get_or_create(qpr_record=record)
    s6.region_a_hindi_bilingual = _convert_to_int(details.get('s6_a_hindi'))
    s6.region_a_english_only = _convert_to_int(details.get('s6_a_eng'))
    s6.region_a_total = _convert_to_int(details.get('s6_a_total'))
    s6.region_b_hindi_bilingual = _convert_to_int(details.get('s6_b_hindi'))
    s6.region_b_english_only = _convert_to_int(details.get('s6_b_eng'))
    s6.region_b_total = _convert_to_int(details.get('s6_b_total'))
    s6.region_c_hindi_bilingual = _convert_to_int(details.get('s6_c_hindi'))
    s6.region_c_english_only = _convert_to_int(details.get('s6_c_eng'))
    s6.region_c_total = _convert_to_int(details.get('s6_c_total'))
    s6.save()
    # Section 7
    s7, _ = Section7NotingsData.objects.get_or_create(qpr_record=record)
    s7.hindi_pages = _convert_to_int(details.get('s7_hindi'))
    s7.english_pages = _convert_to_int(details.get('s7_eng'))
    s7.total_pages = _convert_to_int(details.get('s7_total'))
    s7.eoffice_notings = _convert_to_int(details.get('s7_eoffice'))
    s7.save()
    # Section 8
    s8, _ = Section8WorkshopsData.objects.get_or_create(qpr_record=record)
    s8.full_day_workshops = _convert_to_int(details.get('s8_workshops'))
    s8.officers_trained = _convert_to_int(details.get('s8_officers'))
    s8.employees_trained = _convert_to_int(details.get('s8_employees'))
    s8.save()
    # Section 9
    s9, _ = Section9ImplementationCommitteeData.objects.get_or_create(qpr_record=record)
    s9.meeting_date = _convert_to_date(details.get('s9_date'))
    s9.sub_committees_count = _convert_to_int(details.get('s9_sub_committees'))
    s9.meetings_organized = _convert_to_int(details.get('s9_meetings_count'))
    s9.agenda_hindi = details.get('s9_agenda_hindi', '')
    s9.save()
    # Section 10
    s10, _ = Section10HindiAdvisoryData.objects.get_or_create(qpr_record=record)
    s10.meeting_date = _convert_to_date(details.get('s10_date'))
    s10.save()
    # Section 11
    s11, _ = Section11SpecificAchievementsData.objects.get_or_create(qpr_record=record)
    s11.innovative_work = details.get('s12_1', '')
    s11.special_events = details.get('s12_2', '')
    s11.hindi_medium_works = details.get('s12_3', '')
    s11.save()

def serialize_qpr_record(record):
    """Serialize a QPRRecord with all related sections."""
    data = {
        'id': record.id,
        'officeName': record.officeName,
        'officeCode': record.officeCode,
        'region': record.region,
        'quarter': record.quarter,
        'year': record.year or '2025-2026',
        'status': record.status,
        'is_submitted': record.is_submitted,
        'details': {}
    }
    return data

def send_otp_email(user, lang):
    user.otp = str(random.randint(100000, 999999))
    user.otp_created_at = timezone.now()
    user.save(update_fields=['otp', 'otp_created_at'])
    send_system_email(user, None, 'otp', extra_context={'otp': user.otp, 'lang': lang})
    return user.otp


def custom_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')

def home(request):
    return render(request, 'home.html')

def universal_error_view(request, exception=None, status_code=500):
    lang = request.session.get('lang', 'en')
    error_map = {
        400: {'title': "Bad Request",'msg': "The server could not understand the request due to invalid syntax."},
        403: {'title': "Security Verification Failed",'msg': "You do not have permission to access this resource or your session has expired."},
        404: {'title': "Page Not Found",'msg': "The page you are looking for might have been removed or does not exist."},
        500: {'title': "Internal Server Error",'msg': "Something went wrong on our end. We're working on fixing it."}
    }
    config = error_map.get(status_code, error_map[500])
    context = {'current_lang': lang, 'status_code': status_code, 'error_title': config['title'], 'error_message': config['msg']}
    return render(request, 'error.html', context, status=status_code)

def error_400(request, exception=None): return universal_error_view(request, exception, 400)
def error_403(request, exception=None): return universal_error_view(request, exception, 403)
def csrf_failure(request, reason=""): return universal_error_view(request, None, 403)
def error_404(request, exception=None): return universal_error_view(request, exception, 404)
def error_500(request): return universal_error_view(request, None, 500)

@login_required
def dashboard(request):
    user = request.user
    role = request.session.get('active_role', user.role)
    
    context = {
        'current_lang': request.session.get('lang', 'en'),
        'role': role
    }

    # 1. ADMIN VIEW
    if role == 'admin':
        # Calculate HOD Stats
        hod_stats = []
        hod_users = User.objects.filter(role='hod', is_active=True)
        
        for hod in hod_users:
            emps = UserProfile.objects.filter(hod_name=hod.username)
            total = emps.count()
            if total > 0:
                prof_ok = emps.filter(profile_updated=True).count()
                user_ids = emps.values_list('user_id', flat=True)
                qpr_ok = QPRRecord.objects.filter(user_id__in=user_ids, is_submitted=True).count()
                completion = round((qpr_ok / total) * 100, 1)
                
                hod_stats.append({
                    'hod_name': hod.username,
                    'total_employees': total,
                    'profile_completed': prof_ok,
                    'qpr_completed': qpr_ok,
                    'completion_percentage': completion
                })

        context.update({
            # Show ONLY active users in the main list
            'users': User.objects.exclude(role='admin').filter(is_active=True, is_archived=False).order_by('-date_joined'),
            
            # Show DEACTIVATED/ARCHIVED users in the repository
            # We filter by is_archived=True (Soft Deleted Users)
            'archived_users': User.objects.filter(is_archived=True).order_by('-date_joined'),
            
            'manager_requests': ManagerRequest.objects.filter(status='pending'),
            'hod_stats': hod_stats,
        })
        return render(request, 'dashboard.html', context)

    # ... (Keep Manager, HOD, Backup, and User blocks exactly as they were) ...
    elif role == 'manager':
        employees = Employee.objects.all().order_by('-lastupdate')
        context.update({
            'employees': employees,
            'users': User.objects.filter(role='user'), 
        })
        return render(request, 'dashboard.html', context)

    elif role == 'hod':
        my_users = UserProfile.objects.filter(hod_name=user.username)
        total = my_users.count()
        qpr_submitted = QPRRecord.objects.filter(user__profile__in=my_users, is_submitted=True).count()
        profile_updated = my_users.filter(profile_updated=True).count()
        context.update({
            'total_users': total,
            'qpr_submitted': qpr_submitted,
            'qpr_pending': total - qpr_submitted,
            'profile_updated': profile_updated,
            'hod_name': user.username
        })
        return render(request, 'dashboard.html', context)
        
    elif role == 'backup_user':
        return render(request, 'dashboard.html', context)

    else: # Standard User
        try:
            profile = user.profile
            qpr_submitted = QPRRecord.objects.filter(user=user, is_submitted=True).exists()
            context.update({
                'profile': profile,
                'qpr_submitted': qpr_submitted,
                'profile_status': "Complete" if profile.profile_updated else "Incomplete"
            })
        except UserProfile.DoesNotExist:
            context.update({'error': "Profile not found."})
        return render(request, 'dashboard.html', context)

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def toggle_language(request):
    current = request.session.get('lang', 'en')
    request.session['lang'] = 'hi' if current == 'en' else 'en'
    return redirect(request.META.get('HTTP_REFERER', 'home'))

class CustomLoginView(LoginView):
    authentication_form = CustomLoginForm
    template_name = 'registration/login.html'

    def get_success_url(self):
        return reverse('dashboard')

    def form_valid(self, form):
        user = form.get_user()
        auth_login(self.request, user)
        selected_role = form.cleaned_data.get('role')
        current_lang = self.request.session.get('lang', 'en')
        user.role = selected_role
        user.save(update_fields=['role'])
        self.request.session['lang'] = current_lang
        self.request.session['active_role'] = selected_role
        self.request.session.save()
        send_system_email(user, self.request, 'login')
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        username = form.data.get('username')
        user = CustomUser.objects.filter(username=username).first()
        if user and not user.is_active and user.check_password(form.data.get('password')):
            lang = self.request.session.get('lang', 'en')
            messages.error(self.request, translate_text("Your account has been archived. Please contact the admin.", lang))
            return self.render_to_response(self.get_context_data(form=form))
        return super().form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'request': self.request})
        return kwargs

def signup(request):
    """Updated Signup with OTP Verification"""
    if request.user.is_authenticated: 
        return redirect('dashboard')
    
    lang = request.session.get('lang', 'en')
    form = CustomUserCreationForm(request.POST or None, request=request)
    
    if request.method == "POST":
        if form.is_valid():
            # 1. Create user but keep inactive
            user = form.save(commit=False)
            user.is_active = False  
            user.save()
            
            # 2. Generate and Send OTP
            send_otp_email(user, lang)
            
            # 3. Setup Session for VerifyOTPView
            email = user.get_email()
            email_hash = hashlib.sha256(email.encode()).hexdigest()
            request.session['reset_email_hash'] = email_hash
            request.session['is_signup'] = True  # Flag for VerifyOTPView
            
            messages.success(request, "Account created! Please verify your email.")
            return redirect('verify_otp')
        else:
            messages.error(request, "Please correct the errors below.")
    
    return render(request, 'registration/signup.html', {'form': form})

# ==================== PASSWORD & OTP ====================

class ForgotPasswordView(View):
    def get(self, request):
        return render(request, 'registration/forgot_password.html')
    def post(self, request):
        lang = request.session.get('lang', 'en')
        username = request.POST.get('username', '').strip()
        user = CustomUser.objects.filter(username=username).first()
        if user:
            send_otp_email(user, lang)
            email = user.get_email()
            if email:
                request.session['reset_email_hash'] = hashlib.sha256(email.encode()).hexdigest()
                messages.success(request, translate_text("OTP sent successfully.", lang))
                return redirect('verify_otp')
        messages.error(request, translate_text("User does not exist.", lang))
        return redirect('forgot_password')

class VerifyOTPView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash'): return redirect('forgot_password')
        lang = request.session.get('lang', 'en')
        context = {'title_text': translate_text("Verify OTP", lang), 'button_text': translate_text("Verify Code", lang), 'current_lang': lang}
        return render(request, 'registration/verify_otp.html', context)
    def post(self, request):
        email_hash = request.session.get('reset_email_hash')
        otp_input = request.POST.get('otp')
        lang = request.session.get('lang', 'en')
        att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
        
        if cache.get(blk_key):
            return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})
        
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        
        if user and user.otp == otp_input:
            if (timezone.now() - user.otp_created_at).total_seconds() < 300:
                
                # Signup Verification Logic
                if request.session.get('is_signup'):
                    user.is_active = True
                    user.otp = None
                    user.save()
                    
                    # Auto-create profile & mark updated
                    profile, _ = UserProfile.objects.get_or_create(
                        user=user,
                        defaults={"employee_code": user.username, "role": "user"}
                    )
                    profile.profile_updated = True
                    profile.save()

                    if not Employee.objects.filter(empcode=user.username).exists():
                        Employee.objects.create(empcode=user.username, ename=user.first_name or "", status='draft')
                    
                    # Login
                    user.backend = 'django.contrib.auth.backends.ModelBackend'
                    auth_login(request, user)
                    
                    request.session['lang'] = lang
                    request.session['active_role'] = 'user'
                    send_system_email(user, request, 'welcome')
                    
                    request.session.pop('reset_email_hash', None)
                    request.session.pop('is_signup', None)
                    
                    messages.success(request, "Email verified! Welcome.")
                    return redirect('dashboard')

                # Password Reset Logic
                request.session['otp_verified'] = True
                return redirect('reset_password')
        
        attempts = cache.get(att_key, 0) + 1
        cache.set(att_key, attempts, 600)
        if attempts >= 5: cache.set(blk_key, True, 600)
        messages.error(request, translate_text("Invalid or expired OTP.", lang))
        return render(request, 'registration/verify_otp.html', {'current_lang': lang})

class ResendOTPView(View):
    def get(self, request):
        email_hash = request.session.get('reset_email_hash')
        if not email_hash: return redirect('forgot_password')
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        if not user: return redirect('forgot_password')
        lang = request.session.get('lang', 'en')
        send_otp_email(user, lang)
        messages.success(request, translate_text("New OTP sent.", lang))
        return redirect('verify_otp')

class ResetPasswordView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash'): return redirect('forgot_password')
        return render(request, 'registration/reset_password.html')
    def post(self, request):
        email_hash = request.session.get('reset_email_hash')
        pwd = request.POST.get('password')
        cfm = request.POST.get('confirm_password')
        if not email_hash: return redirect('forgot_password')
        if pwd == cfm:
            user = CustomUser.objects.filter(email_hash=email_hash).first()
            if user:
                user.set_password(pwd)
                user.otp = None
                user.save()
                send_system_email(user, request, 'reset')
                request.session.pop('reset_email_hash', None)
                messages.success(request, "Password reset successfully.")
            return redirect('login')
        messages.error(request, "Passwords do not match.")
        return render(request, 'registration/reset_password.html')

@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect')
        elif new_password1 != new_password2:
            messages.error(request, 'New passwords do not match')
        elif len(new_password1) < 6:
            messages.error(request, 'New password must be at least 6 characters')
        else:
            request.user.set_password(new_password1)
            request.user.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('dashboard')
    return render(request, 'qpr/change_password.html')

# ==================== DATA & PRIVACY & ARCHIVING (RESTORED) ====================

@login_required
def user_detail_view(request, user_id):
    """Restored User Detail View with Access Logging"""
    target_user = get_object_or_404(CustomUser, id=user_id)
    lang = request.session.get('lang', 'en')
    active_role = request.session.get('active_role', 'user')
    if request.user != target_user and active_role in ['admin', 'manager']:
        DataAccessLog.objects.create(
            accessed_by=request.user,
            target_user=target_user,
            reason="Manager/Admin Dashboard Review"
        )
    return render(request, 'user_detail.html', {
        'target_user': target_user,
        'current_lang': lang,
        'role': active_role
    })

@login_required
def export_user_data(request):
    user = request.user
    send_system_email(user, request, 'export')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{user.username}_data.csv"'
    writer = csv.writer(response)
    writer.writerow(['Category', 'Value'])
    writer.writerow(['Username', user.username])
    writer.writerow(['Email', user.get_email()])
    return response

@login_required
def delete_account(request):
    if request.method == "POST":
        request.user.delete()
        logout(request)
        messages.success(request, "Your personal data has been erased successfully.")
        return redirect('login')
    return render(request, 'registration/confirm_erasure.html')

@user_passes_test(lambda u: u.is_superuser)
def download_privacy_audit(request):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "DPDP Privacy Audit Report")
    y = height - 100
    logs = DataAccessLog.objects.all().order_by('-access_time')
    for log in logs:
        p.setFont("Helvetica", 10)
        p.drawString(50, y, f"{log.access_time.strftime('%Y-%m-%d')}: {log.accessed_by.username} accessed {log.target_user.username}")
        y -= 20
        if y < 50:
            p.showPage()
            y = height - 50
    p.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'privacy_audit_{timezone.now().date()}.pdf')

@user_passes_test(lambda u: u.is_superuser)
def privacy_audit_report(request):
    logs = DataAccessLog.objects.all().order_by('-access_time')
    lang = request.session.get('lang', 'en')
    return render(request, 'privacy_audit.html', {'logs': logs, 'current_lang': lang})

@login_required
def download_db_backup(request):
    if request.session.get('active_role') != 'backup_user':
        messages.error(request, "Unauthorized access.")
        return redirect('dashboard')
    db_path = settings.DATABASES['default']['NAME']
    if os.path.exists(db_path):
        return FileResponse(open(db_path, 'rb'), as_attachment=True, filename='backup_RajyaBhasha.sqlite3')
    messages.error(request, "Database file not found.")
    return redirect('dashboard')

# ==================== ARCHIVE HELPERS (RESTORED) ====================

@login_required
@user_passes_test(is_admin)  # This checks user.role == 'admin', so NO Superuser required
def archive_user(request, user_id):  # ✅ FIXED: Added 'request' argument
    # 1. Fetch User
    user_to_archive = get_object_or_404(CustomUser, id=user_id)
    
    # 2. Prevent archiving yourself
    if user_to_archive.id == request.user.id:
        messages.error(request, "You cannot archive yourself.")
        return redirect('dashboard')

    # 3. Create Snapshot for Archive
    employee = Employee.objects.filter(empcode=user_to_archive.username).first()
    snapshot = {}
    if employee:
        snapshot = {
            "name": employee.ename,
            "designation": employee.designation,
            "status": employee.status,
            "last_updated": str(employee.lastupdate)
        }

    # 4. Create Archive Record
    ArchivedUser.objects.create(
        username=user_to_archive.username,
        email_hash=user_to_archive.email_hash,
        encrypted_email_data=user_to_archive.encrypted_email_data,
        original_user_id=user_to_archive.id,
        employee_snapshot=json.dumps(snapshot) 
    )
    
    # 5. Soft Delete (Deactivate)
    user_to_archive.is_active = False    
    user_to_archive.is_archived = True
    user_to_archive.save()

    # 6. Success Message & Redirect
    messages.success(request, f"User {user_to_archive.username} has been archived successfully.")
    return redirect('dashboard')  # ✅ FIXED: Added return statement

@login_required
@user_passes_test(is_admin)
def unarchive_user(request, archive_id):
    """ Restores a user from Archive """
    archived_record = get_object_or_404(ArchivedUser, id=archive_id)
    
    try:
        user_to_restore = CustomUser.objects.get(id=archived_record.original_user_id)
        user_to_restore.is_active = True
        user_to_restore.is_archived = False
        user_to_restore.save()
        
        # Cleanup Archive Record
        archived_record.delete()
        
        messages.success(request, f"User {user_to_restore.username} has been unarchived/restored.")
        return redirect('dashboard')
        
    except CustomUser.DoesNotExist:
        # Fallback if the original user was actually deleted
        messages.error(request, "Original user record not found. Cannot restore.")
        return redirect('dashboard')

@login_required
def profile_view(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    if request.method == 'POST':
        new_email = request.POST.get('email', '').lower().strip()
        if user.is_frozen and not user.is_edit_allowed:
            messages.error(request, translate_text("Profile is frozen.", lang), extra_tags='danger')
            return redirect('dashboard')
        email_hash = hashlib.sha256(new_email.encode()).hexdigest()
        if CustomUser.objects.filter(email_hash=email_hash).exclude(pk=user.pk).exists():
            messages.error(request, translate_text("Email already in use.", lang), extra_tags='danger')
        else:
            user.set_email(new_email)
            if user.is_edit_allowed: user.is_edit_allowed = False
            user.save()
            send_system_email(user, request, 'update')
            messages.success(request, translate_text("Profile updated successfully!", lang))
    return redirect('dashboard')

@login_required
def user_profile(request):
    """QPR specific profile"""
    profile = request.user.profile
    profile_submitted = profile.profile_updated
    profile_edit_approved = False
    profile_edit_pending = False
    if profile_submitted:
        approved_request = ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='approved').first()
        profile_edit_approved = approved_request is not None
        pending_request = ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='pending').first()
        profile_edit_pending = pending_request is not None

    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, 'Email is required')
        elif profile_submitted and not profile_edit_approved:
            messages.error(request, 'You cannot edit a submitted profile. Please request approval from Admin first.')
        else:
            profile.email = email
            profile.profile_updated = True
            profile.save()
            request.user.email = email
            request.user.save()
            if profile_edit_approved:
                ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='approved').delete()
            messages.success(request, 'Profile updated successfully!')
            return redirect('qpr_user_dashboard')

    context = {
        'profile': profile,
        'profile_updated': profile.profile_updated,
        'profile_edit_approved': profile_edit_approved,
        'profile_edit_pending': profile_edit_pending,
        'can_edit': not profile_submitted or profile_edit_approved,
    }
    return render(request, 'profile.html', context)

@login_required
def freeze_profile(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    user.is_frozen = True
    user.save()
    send_system_email(user, request, 'freeze')
    messages.success(request, translate_text("Your profile has been frozen.", lang))
    return redirect('dashboard')

@login_required
def request_edit(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    if not user.is_frozen: return redirect('dashboard')
    manager = CustomUser.objects.filter(role='manager').first()
    if manager:
        msg = f"User {user.username} has requested permission to edit their profile."
        send_system_email(manager, request, 'manager_alert', extra_context={'body_text': msg})
        messages.success(request, translate_text("Edit request sent to manager.", lang))
    else:
        messages.error(request, translate_text("No manager found.", lang))
    return redirect('dashboard')

@login_required
def user_office_form(request):
    profile = request.user.profile
    if request.method == 'POST':
        office_name = request.POST.get('office_name', '')
        office_code = request.POST.get('office_code', '')
        if not office_name or not office_code:
            messages.error(request, 'Office name and code are required')
        else:
            profile.office_name = office_name
            profile.office_code = office_code
            profile.save()
            messages.success(request, 'Office details updated successfully!')
            return redirect('qpr_user_dashboard')
    context = {'profile': profile}
    return render(request, 'user_office_form.html', context)

# ==================== UNIFIED DASHBOARD VIEWS ====================

@login_required
def user_dashboard(request):
    """User Dashboard View - Unified"""
    profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"employee_code": f"EMP{request.user.id}", "role": request.user.role}
    )    
    qpr_records = QPRRecord.objects.filter(user=request.user)
    submitted_qprs = qpr_records.filter(is_submitted=True).count()
    context = {
        'profile': profile,
        'profile_status': 'Updated' if profile.profile_updated else 'Needs Update',
        'qpr_submitted': submitted_qprs > 0, 
        'qpr_count': qpr_records.count(),
        'user': request.user
    }
    return render(request, 'dashboard.html', context) 
@login_required
def qpr_hod_dashboard(request):
    """HOD Dashboard View - Unified"""
    if request.user.profile.role != 'hod': return redirect('/')
    hod_name = request.user.profile.hod_name
    users_under_hod = UserProfile.objects.filter(role='user', hod_name=hod_name)
    total_users = users_under_hod.count()
    qpr_submitted_count = 0
    profile_updated_count = 0
    for user_profile in users_under_hod:
        if user_profile.user.qpr_records.filter(is_submitted=True).exists():
            qpr_submitted_count += 1
        if user_profile.profile_updated:
            profile_updated_count += 1
    qpr_pending = total_users - qpr_submitted_count
    context = {
        'total_users': total_users,
        'qpr_submitted': qpr_submitted_count, 
        'qpr_pending': qpr_pending,
        'profile_updated': profile_updated_count,
        'hod_name': hod_name
    }
    return render(request, 'dashboard.html', context) 

@login_required
def manager_dashboard(request):
    if not (request.user.role in ['manager', 'admin'] or request.user.is_superuser):
        return redirect('/')
    
    users = CustomUser.objects.all().order_by('-date_joined')
    raw_employees = Employee.objects.all().order_by('-lastupdate')
    
    employee_data = []
    
    for emp in raw_employees:
        # --- 1. ROBUST USER LOOKUP ---
        # Try exact match first
        user = CustomUser.objects.filter(username=emp.empcode).first()
        
        # If not found, convert Integer to String (e.g., 101 -> "101")
        if not user:
            user = CustomUser.objects.filter(username=str(emp.empcode)).first()
            
        # If still not found, try removing spaces (e.g., " 101 " -> "101")
        if not user:
            clean_code = str(emp.empcode).strip()
            user = CustomUser.objects.filter(username=clean_code).first()
        
        # --- 2. QPR DATA ---
        qpr_status_text = "Not Started"
        qpr_is_submitted = False
        latest_qpr_id = None
        qpr_last_updated = None
        
        # Get ID safely
        linked_user_id = user.id if user else None
        
        if user:
            latest_qpr = QPRRecord.objects.filter(user=user).order_by('-updated_at').first()
            if latest_qpr:
                qpr_is_submitted = latest_qpr.is_submitted
                qpr_status_text = "Submitted" if qpr_is_submitted else "Draft"
                latest_qpr_id = latest_qpr.id
                qpr_last_updated = latest_qpr.updated_at

        employee_data.append({
            'empcode': emp.empcode,
            'name': emp.ename,
            'designation': emp.designation,
            'hname': emp.hname,
            'user_id': linked_user_id, # This enables the buttons
            'status': emp.status,
            'lastupdate': emp.lastupdate,
            'qpr_status': qpr_status_text,
            'qpr_is_submitted': qpr_is_submitted,
            'qpr_id': latest_qpr_id,
            'qpr_last_updated': qpr_last_updated
        })

    context = {
        'users': users, 
        'employees': employee_data
    }
    return render(request, 'dashboard.html', context)

@login_required
def manage_user_action(request, user_id, action):
    # ==========================================
    # 1. HANDLE QPR ACTIONS (Uses QPR ID)
    # ==========================================
    if action == 'unlock_qpr':
        # Check permissions
        if not (request.user.role in ['manager', 'admin'] or request.user.is_superuser):
            messages.error(request, "Unauthorized")
            return redirect('dashboard')
            
        try:
            # Here 'user_id' is actually the QPR Record ID
            qpr = QPRRecord.objects.get(id=user_id)
            qpr.is_submitted = False
            qpr.status = "Draft"
            qpr.save()
            messages.success(request, "QPR Form unlocked successfully.")
        except QPRRecord.DoesNotExist:
            messages.error(request, "QPR Record not found.")
        return redirect('dashboard')

    # ==========================================
    # 2. HANDLE USER ACTIONS (Uses User ID)
    # ==========================================
    # Now it is safe to look for the user
    target_user = get_object_or_404(CustomUser, id=user_id)
    lang = request.session.get('lang', 'en')

    # A. Unlock Employee Profile (Uses User -> Employee Lookup)
    if action == 'unlock_record':
        # Robust Lookup: Try strict match, then string conversion match
        employee = Employee.objects.filter(empcode=target_user.username).first()
        
        if not employee:
            # Fallback: username might be string "101" while empcode is int 101 or vice versa
            employee = Employee.objects.filter(empcode=str(target_user.username)).first()

        if employee:
            employee.status = 'draft'
            employee.save()
            
            # Also allow user to edit profile (email/etc)
            target_user.is_edit_allowed = True
            target_user.save()
            
            messages.success(request, f"Employee Record for {target_user.username} unlocked.")
        else:
            messages.error(request, f"No Employee Record found linked to user: {target_user.username}")

    # B. Admin Archive Actions
    elif action == 'archive':
        if request.user.role != 'admin':
            messages.error(request, "Only Admins can archive.")
        else:
            target_user.is_active = False
            target_user.is_archived = True
            target_user.save()
            messages.success(request, "User archived.")

    elif action == 'unarchive':
        if request.user.role != 'admin':
            messages.error(request, "Only Admins can restore.")
        else:
            target_user.is_active = True
            target_user.is_archived = False
            target_user.save()
            messages.success(request, "User restored.")

    return redirect('dashboard')

@login_required
def admin_dashboard(request):
    if request.user.profile.role != 'admin': return redirect('/')
    hod_stats = []
    hods = UserProfile.objects.filter(role='hod').order_by('name')
    for hod_profile in hods:
        hod_key = hod_profile.hod_name or hod_profile.name or hod_profile.employee_code
        hod_display = hod_profile.name or hod_key or 'UNKNOWN'
        users_under_hod = UserProfile.objects.filter(role='user', hod_name__iexact=hod_key)
        total_users = users_under_hod.count()
        profile_complete = sum(1 for p in users_under_hod if p.profile_updated)
        qpr_complete = sum(1 for p in users_under_hod if QPRRecord.objects.filter(user=p.user, status='Submitted').exists())
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        hod_stats.append({
            'hod_name': str(hod_display).upper(),
            'total_employees': total_users,
            'profile_completed': profile_complete,
            'qpr_completed': qpr_complete,
            'completion_percentage': completion_pct,
        })
    unique_hod_names = set(UserProfile.objects.filter(role='user').exclude(hod_name__isnull=True).values_list('hod_name', flat=True))
    actual_hod_names = set(UserProfile.objects.filter(role='hod').values_list('hod_name', flat=True))
    uncovered = unique_hod_names - actual_hod_names
    for hod_name in sorted(uncovered):
        users_under_hod = UserProfile.objects.filter(role='user', hod_name__iexact=hod_name)
        total_users = users_under_hod.count()
        qpr_complete = sum(1 for p in users_under_hod if QPRRecord.objects.filter(user=p.user, status='Submitted').exists())
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        hod_stats.append({
            'hod_name': str(hod_name).upper(),
            'total_employees': total_users,
            'profile_completed': sum(1 for p in users_under_hod if p.profile_updated),
            'qpr_completed': qpr_complete,
            'completion_percentage': completion_pct,
        })
    # 3. Pending Requests
    pending_requests = ManagerRequest.objects.filter(status='pending', hod__profile__role='user')
    context = {'hod_stats': hod_stats, 'manager_requests': pending_requests}
    return render(request, 'dashboard.html', context) # Renders UNIFIED DASHBOARD

# ==================== ADMIN/MANAGER ACTIONS (RESTORED) ====================

@login_required
def admin_create_hod(request):
    if request.user.profile.role != 'admin': return redirect('/')
    if request.method == 'POST':
        emp_code = request.POST.get('emp_code', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = '123456'
        if not emp_code or not first_name or not email:
            messages.error(request, 'All fields required')
        elif UserProfile.objects.filter(employee_code=emp_code).exists() or User.objects.filter(username=emp_code).exists():
            messages.error(request, 'User/Employee code already exists')
        else:
            try:
                user = User.objects.create_user(username=emp_code, password=password, email=email, first_name=first_name)
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.role = 'hod'
                profile.hod_name = first_name
                profile.name = first_name
                profile.employee_code = emp_code
                profile.profile_updated = True
                profile.save()
                messages.success(request, f'HOD {first_name} created!')
                return redirect('qpr_admin_dashboard')
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
    return render(request, 'qpr/admin_create_hod.html')

@login_required
def admin_approve_request(request, request_id):
    if request.user.profile.role != 'admin': return redirect('/')
    try:
        req = ManagerRequest.objects.get(id=request_id)
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'approve':
                req.status = 'approved'
                req.save()
                messages.success(request, 'Approved!')
            elif action == 'reject':
                req.status = 'rejected'
                req.save()
                messages.success(request, 'Rejected!')
        return redirect('qpr_admin_dashboard')
    except ManagerRequest.DoesNotExist:
        return redirect('qpr_admin_dashboard')

@login_required
def admin_employee_list(request):
    if request.user.profile.role != 'admin': return redirect('/')
    employee_code_filter = request.GET.get('employee_code', '').strip()
    name_filter = request.GET.get('name', '').strip()
    hods = UserProfile.objects.filter(role='hod').order_by('name')
    hod_groups = []
    for hod_profile in hods:
        users_under_hod = UserProfile.objects.filter(role='user', hod_name=hod_profile.hod_name).order_by('name')
        user_details = []
        for user_profile in users_under_hod:
            if employee_code_filter and employee_code_filter.lower() not in user_profile.employee_code.lower(): continue
            user_name = user_profile.name or user_profile.user.get_full_name() or user_profile.user.username
            if name_filter and name_filter.lower() not in user_name.lower(): continue
            qpr_records = QPRRecord.objects.filter(user=user_profile.user).order_by('-id')
            latest_qpr = qpr_records.first() if qpr_records else None
            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_name,
                'email': user_profile.user.email,
                'office_name': user_profile.office_name or (latest_qpr.officeName if latest_qpr else 'Not Set'),
                'quarter': latest_qpr.quarter if latest_qpr else 'Not Set',
                'qpr_status': latest_qpr.status if latest_qpr else 'Not Submitted',
            })
        if user_details:
            hod_groups.append({'hod_name': hod_profile.hod_name, 'user_count': len(user_details), 'users': user_details})
    return render(request, 'qpr/admin_employee_list.html', {'hod_groups': hod_groups})

@user_passes_test(lambda u: u.role in ['manager', 'admin'])
def update_designation(request, user_id):
    if request.method == "POST":
        target_user = get_object_or_404(CustomUser, id=user_id)
        new_desig = request.POST.get('designation')
        emp = Employee.objects.filter(empcode=target_user.username).first()
        if emp:
            emp.designation = new_desig
            emp.save()
            messages.success(request, "Designation updated.")
        else:
            messages.error(request, "Employee record not found.")
    return redirect('manager_dashboard')

@user_passes_test(lambda u: u.is_authenticated and (u.role in ['manager', 'admin'] or u.is_superuser))
def manage_user_action(request, user_id, action):
    """Restored Full Action Logic: Archive, Unarchive, Unlock"""
    target_user = get_object_or_404(CustomUser, id=user_id)
    lang = request.session.get('lang', 'en')
    
    if action in ['archive', 'unarchive']:
        if request.user.role != 'admin' and not request.user.is_superuser:
            messages.error(request, translate_text("Only Admins can perform this action.", lang))
            return redirect('manager_dashboard')
        
        if action == 'archive':
            target_user.is_active = False
            target_user.is_archived = True
            target_user.save()
            messages.success(request, translate_text("User archived.", lang))
        elif action == 'unarchive':
            target_user.is_active = True
            target_user.is_archived = False
            target_user.save()
            messages.success(request, translate_text("User restored.", lang))

    # 2. Manager Actions
    elif action == 'unlock_record':
        emp = Employee.objects.filter(empcode=target_user.username).first()
        if emp:
            emp.status = 'draft'
            emp.save()
            target_user.is_edit_allowed = True
            target_user.save()
            messages.success(request, "Record unlocked.")
    return redirect('manager_dashboard')

# ==================== QPR REPORTING & HOD ====================

@login_required
def qpr_form(request):
    return render(request, 'qpr/qpr_form.html')

@login_required
def report_list(request):
    return render(request, 'qpr/report_list.html')
@login_required
def report_detail(request, record_id):
    return render(request, 'qpr/report_detail.html', {'record_id': record_id})

@login_required
def hod_detail_list(request):
    if request.user.profile.role != 'hod': return redirect('/')
    hod_name = request.user.profile.hod_name
    users_under_hod = UserProfile.objects.filter(role='user', hod_name=hod_name).select_related('user')
    users_data = []
    for user_profile in users_under_hod:
        user = user_profile.user
        qpr_records = user.qpr_records.all()
        office_code = ''
        office_name = ''
        if qpr_records.exists():
            first_qpr = qpr_records.first()
            office_code = first_qpr.officeCode
            office_name = first_qpr.officeName
        has_pending = ManagerRequest.objects.filter(hod=user, request_type='qpr', status='pending').exists()
        users_data.append({
            'profile': user_profile, 'user': user, 'employee_code': user_profile.employee_code,
            'name': user_profile.name, 'office_code': office_code, 'office_name': office_name,
            'profile_complete': user_profile.profile_updated, 'qpr_complete': qpr_records.filter(is_submitted=True).exists(),
            'has_pending_edit_request': has_pending
        })
    context = {'users_data': users_data, 'hod_name': hod_name}
    return render(request, 'qpr/hod_detail_list.html', context)

@login_required
def hod_manager_requests(request):
    if request.user.profile.role != 'hod': return redirect('/')
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        request_type = request.POST.get('request_type')
        reason = request.POST.get('reason', '')
        try:
            user = User.objects.get(id=user_id)
            if user.profile.hod_name != request.user.profile.hod_name:
                messages.error(request, 'User is not under your HOD group')
            else:
                ManagerRequest.objects.create(hod=request.user, user=user, request_type=request_type, reason=reason)
                messages.success(request, 'Request sent successfully!')
        except User.DoesNotExist:
            messages.error(request, 'User not found')
    hod_name = request.user.profile.hod_name
    users_under_hod = UserProfile.objects.filter(role='user', hod_name=hod_name)
    users_data = [{'user': u.user, 'name': u.name, 'employee_code': u.employee_code} for u in users_under_hod]
    return render(request, 'qpr/hod_manager_requests.html', {'users_data': users_data})

# ==================== APIs ====================

@csrf_exempt
@login_required
def api_records(request):
    if not request.user.is_authenticated: return JsonResponse({'error': 'Unauthorized'}, status=401)
    if request.method == 'GET':
        records = QPRRecord.objects.filter(user=request.user).order_by('-id')
        data = []
        for record in records:
            d = serialize_qpr_record(record)
            edit_approved = False
            if record.is_submitted:
                edit_approved = ManagerRequest.objects.filter(hod=request.user, request_type='qpr', status='approved').exists()
            d['can_edit'] = not record.is_submitted or edit_approved
            d['edit_approved'] = edit_approved
            data.append(d)
        return JsonResponse(data, safe=False)
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            record_id = data.get('id')
            details = data.get('details', {})
            if record_id:
                record = QPRRecord.objects.get(pk=record_id, user=request.user)
                record.officeName = data.get('officeName', '')
                record.officeCode = data.get('officeCode', '')
                record.region = data.get('region', '')
                record.quarter = data.get('quarter', '')
                record.status = data.get('status', 'Draft')
                record.phone = data.get('phone', '')
                record.email = data.get('email', '')
                record.is_submitted = (record.status == 'Submitted')
                record.save()
                if record.is_submitted:
                    ManagerRequest.objects.filter(hod=request.user, request_type='qpr', status='approved').delete()
                _save_section_data(record, details)
            else:
                is_submitted = (data.get('status', 'Draft') == 'Submitted')
                record = QPRRecord.objects.create(
                    user=request.user, officeName=data.get('officeName', ''), officeCode=data.get('officeCode', ''),
                    region=data.get('region', ''), quarter=data.get('quarter', ''), status=data.get('status', 'Draft'),
                    phone=data.get('phone', ''), email=data.get('email', ''), is_submitted=is_submitted
                )
                _save_section_data(record, details)
            return JsonResponse({'id': record.id, 'message': 'Saved successfully!'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    elif request.method == 'DELETE':
        record_id = request.GET.get('id')
        if record_id:
            QPRRecord.objects.filter(pk=record_id, user=request.user).delete()
            return JsonResponse({'message': 'Deleted'})
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
@csrf_exempt
def api_record_detail(request, record_id):
    try:
        record = QPRRecord.objects.get(pk=record_id, user=request.user)
        data = serialize_qpr_record(record)
        return JsonResponse(data, safe=False)
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Record not found'}, status=404)

@login_required
@csrf_exempt
def request_edit_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request_type = data.get('request_type')
            record_id = data.get('record_id')
            reason = data.get('reason', '')
            admin_users = User.objects.filter(profile__role='admin')
            if not admin_users.exists(): return JsonResponse({'success': False, 'error': 'No Admin found'}, status=400)
            for admin_user in admin_users:
                ManagerRequest.objects.create(hod=request.user, user=admin_user, request_type=request_type, reason=f"Edit request: {reason}")
            return JsonResponse({'success': True, 'message': 'Request sent'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=400)

class EmployeeListCreateAPI(APIView):
    def get(self, request):
        if request.session.get('active_role') != 'user': return Response({"error": "Unauthorized"}, status=403)
        status_filter = request.GET.get("status")
        qs = Employee.objects.all().order_by("-lastupdate")
        if status_filter: qs = qs.filter(status=status_filter)
        serializer = EmployeeSerializer(qs, many=True)
        return Response(serializer.data)
    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(lastupdate=timezone.now())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmployeeDetailAPI(APIView):
    def get_object(self, pk):
        try: return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist: return None
    def get(self, request, pk):
        emp = self.get_object(pk)
        if not emp: return Response({"error": "Not found"}, status=404)
        return Response(EmployeeSerializer(emp).data)
    def put(self, request, pk):
        emp = self.get_object(pk)
        if not emp: return Response({"error": "Not found"}, status=404)
        serializer = EmployeeSerializer(emp, data=request.data)
        if serializer.is_valid():
            serializer.save(lastupdate=timezone.now())
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
    def delete(self, request, pk):
        emp = self.get_object(pk)
        if not emp: return Response({"error": "Not found"}, status=404)
        emp.delete()
        return Response({"message": "Deleted"})

class SubmitDraftAPI(APIView):
    def post(self, request):
        ids = request.data.get("ids", [])
        count = Employee.objects.filter(id__in=ids, status="draft").update(status="submitted", lastupdate=timezone.now())
        return Response({"message": f"{count} record(s) submitted"})

@login_required
def employee_form(request):
    if request.session.get('active_role') != 'user': return redirect('dashboard')
    form = EmployeeForm()
    return render(request, "employeeform.html", {"form": form})