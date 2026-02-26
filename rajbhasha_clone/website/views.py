import os,io,csv,random,hashlib,json
from datetime import datetime
from urllib import request
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Count
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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
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
    Section11SpecificAchievementsData, UserProfile, ManagerRequest, EditRequest,
    TypingUsageReport
)
from .forms import CustomLoginForm, CustomUserCreationForm, TypingUsageReportForm
from .employeeform import EmployeeForm
from .serializers import EmployeeSerializer
from .utils import send_system_email
from .templatetags.translate_tags import translate_text
FONT_PATH = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'NIRMALA.TTF')
pdfmetrics.registerFont(TTFont('HindiFont', FONT_PATH))

User = get_user_model()

def is_admin(user):
    return user.is_authenticated and user.role == 'admin'

def get_active_hods():
    """Get list of all active HODs for registration/selection dropdowns"""
    # Get HODs with role='hod'
    hod_names = list(UserProfile.objects.filter(role='hod').values_list('hod_name', flat=True).distinct())
    
    # Also add users with hod_name=None as their own HODs (using their name)
    unassigned_hod_names = list(UserProfile.objects.filter(
        role='user', 
        hod_name__isnull=True
    ).values_list('name', flat=True).distinct())
    
    # Combine and sort
    all_hod_names = sorted(set([h for h in hod_names if h] + [u for u in unassigned_hod_names if u]))
    return all_hod_names

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
        'phone': record.phone or '',
        'email': record.email or '',
        # Section 1
        's1_total': getattr(record.section1, 'total_files', '') if hasattr(record, 'section1') else '',
        's1_hindi': getattr(record.section1, 'hindi_files', '') if hasattr(record, 'section1') else '',
        # Section 2
        's2_meetings': getattr(record.section2, 'meetings_count', '') if hasattr(record, 'section2') else '',
        's2_minutes': getattr(record.section2, 'hindi_minutes', '') if hasattr(record, 'section2') else '',
        's2_papers_total': getattr(record.section2, 'total_papers', '') if hasattr(record, 'section2') else '',
        's2_papers_hindi': getattr(record.section2, 'hindi_papers', '') if hasattr(record, 'section2') else '',
        # Section 3
        's3_total': getattr(record.section3, 'total_documents', '') if hasattr(record, 'section3') else '',
        's3_bilingual': getattr(record.section3, 'bilingual_documents', '') if hasattr(record, 'section3') else '',
        's3_english': getattr(record.section3, 'english_only_documents', '') if hasattr(record, 'section3') else '',
        's3_hindi_only': getattr(record.section3, 'hindi_only_documents', '') if hasattr(record, 'section3') else '',
        # Section 4
        's4_total': getattr(record.section4, 'total_letters', '') if hasattr(record, 'section4') else '',
        's4_no_reply': getattr(record.section4, 'no_reply_letters', '') if hasattr(record, 'section4') else '',
        's4_replied_hindi': getattr(record.section4, 'replied_hindi_letters', '') if hasattr(record, 'section4') else '',
        's4_replied_eng': getattr(record.section4, 'replied_english_letters', '') if hasattr(record, 'section4') else '',
        # Section 5
        's5_total': getattr(record.section5, 'region_a_english_letters', '') if hasattr(record, 'section5') else '',
        's5_hindi': getattr(record.section5, 'region_a_replied_hindi', '') if hasattr(record, 'section5') else '',
        's5_english': getattr(record.section5, 'region_a_replied_english', '') if hasattr(record, 'section5') else '',
        's5_noreply': getattr(record.section5, 'region_a_no_reply', '') if hasattr(record, 'section5') else '',
        # Section 6
        's6_a_hindi': getattr(record.section6, 'region_a_hindi_bilingual', '') if hasattr(record, 'section6') else '',
        's6_a_eng': getattr(record.section6, 'region_a_english_only', '') if hasattr(record, 'section6') else '',
        's6_a_total': getattr(record.section6, 'region_a_total', '') if hasattr(record, 'section6') else '',
        's6_b_hindi': getattr(record.section6, 'region_b_hindi_bilingual', '') if hasattr(record, 'section6') else '',
        's6_b_eng': getattr(record.section6, 'region_b_english_only', '') if hasattr(record, 'section6') else '',
        's6_b_total': getattr(record.section6, 'region_b_total', '') if hasattr(record, 'section6') else '',
        's6_c_hindi': getattr(record.section6, 'region_c_hindi_bilingual', '') if hasattr(record, 'section6') else '',
        's6_c_eng': getattr(record.section6, 'region_c_english_only', '') if hasattr(record, 'section6') else '',
        's6_c_total': getattr(record.section6, 'region_c_total', '') if hasattr(record, 'section6') else '',
        # Section 7
        's7_hindi': getattr(record.section7, 'hindi_notings_pages', '') if hasattr(record, 'section7') else '',
        's7_eng': getattr(record.section7, 'english_notings_pages', '') if hasattr(record, 'section7') else '',
        's7_total': getattr(record.section7, 'total_notings_pages', '') if hasattr(record, 'section7') else '',
        's7_eoffice': getattr(record.section7, 'eoffice_notings', '') if hasattr(record, 'section7') else '',
        # Section 8
        's8_workshops': getattr(record.section8, 'workshops_count', '') if hasattr(record, 'section8') else '',
        's8_officers': getattr(record.section8, 'officers_trained', '') if hasattr(record, 'section8') else '',
        's8_employees': getattr(record.section8, 'employees_trained', '') if hasattr(record, 'section8') else '',
        # Section 9
        's9_date': getattr(record.section9, 'meeting_date', '') if hasattr(record, 'section9') else '',
        's9_sub_committees': getattr(record.section9, 'sub_committees_count', '') if hasattr(record, 'section9') else '',
        's9_meetings_count': getattr(record.section9, 'meetings_count', '') if hasattr(record, 'section9') else '',
        's9_agenda_hindi': getattr(record.section9, 'agenda_in_hindi', '') if hasattr(record, 'section9') else '',
        # Section 10
        's10_date': getattr(record.section10, 'meeting_date', '') if hasattr(record, 'section10') else '',
        # Section 11
        's12_1': getattr(record.section11, 'innovative_work', '') if hasattr(record, 'section11') else '',
        's12_2': getattr(record.section11, 'special_event', '') if hasattr(record, 'section11') else '',
        's12_3': getattr(record.section11, 'other_works', '') if hasattr(record, 'section11') else '',
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
    """Central Dashboard Router - Routes each role to their dedicated dashboard"""
    user = request.user
    role = request.session.get('active_role', user.role)
    
    context = {
        'current_lang': request.session.get('lang', 'en'),
        'role': role
    }

    # 1. ADMIN - System administration, HOD management, archive/unarchive, typing reports
    if role == 'admin':
        return redirect('qpr_admin_dashboard')

    # 2. MANAGER - Edit request approvals, employee records management, designations
    elif role == 'manager':
        return redirect('manager_dashboard')
    
    # 3. HOD - Department oversight, employee statistics, detail list
    elif role == 'hod':
        return redirect('qpr_hod_dashboard')
        
    # 4. BACKUP USER - Database download and backup management
    elif role == 'backup_user':
        return render(request, 'dashboard.html', context)

    # 5. USER (Default) - Profile management, QPR forms, employee forms
    else:
        return redirect('qpr_user_dashboard')

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
    if request.user.is_authenticated: 
        return redirect('dashboard')
    
    lang = request.session.get('lang', 'en')
    form = CustomUserCreationForm(request.POST or None, request=request)
    
    if request.method == "POST":
        if form.is_valid():
            user = form.save(commit=False)
            
            otp = str(random.randint(100000, 999999))
            request.session['signup_data'] = {
                'username': user.username,
                'email': form.cleaned_data['email'],
                'password': user.password, 
                'first_name': user.first_name,
                'otp': otp,
                'otp_time': timezone.now().timestamp()
            }
            request.session['is_signup'] = True
            
            send_system_email(user, request, 'otp', extra_context={'otp': otp, 'lang': lang})
            
            messages.success(request, "Account verification initiated! Please verify your email with the OTP sent.")
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
        if not request.session.get('reset_email_hash') and not request.session.get('is_signup'): 
            return redirect('forgot_password')
        lang = request.session.get('lang', 'en')
        context = {'title_text': translate_text("Verify OTP", lang), 'button_text': translate_text("Verify Code", lang), 'current_lang': lang}
        return render(request, 'registration/verify_otp.html', context)
    def post(self, request):
        otp_input = request.POST.get('otp')
        lang = request.session.get('lang', 'en')
        if request.session.get('is_signup'):
            signup_data = request.session.get('signup_data')
            if not signup_data:
                messages.error(request, "Session expired. Please sign up again.")
                return redirect('signup')
            email_hash = hashlib.sha256(signup_data['email'].encode()).hexdigest()
            att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
            if cache.get(blk_key):
                return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})
            if otp_input == signup_data['otp']:
                if (timezone.now().timestamp() - signup_data['otp_time']) < 300: # 5 min expiry
                    try:
                        user = CustomUser(
                            username=signup_data['username'],
                            password=signup_data['password'],
                            first_name=signup_data.get('first_name', ''),
                            is_active=True,
                            consent_given_at=timezone.now()
                        )
                        user.set_email(signup_data['email'])
                        user.save()
                        profile, _ = UserProfile.objects.get_or_create(
                            user=user,
                            defaults={"employee_code": user.username, "role": "user"}
                        )
                        profile.profile_updated = True
                        profile.save()
                        if not Employee.objects.filter(empcode=user.username).exists():
                            Employee.objects.create(empcode=user.username, ename=user.first_name or "", status='draft')
                        user.backend = 'django.contrib.auth.backends.ModelBackend'
                        auth_login(request, user)
                        request.session['lang'] = lang
                        request.session['active_role'] = 'user'
                        send_system_email(user, request, 'welcome')
                        request.session.pop('signup_data', None)
                        request.session.pop('is_signup', None)
                        messages.success(request, "Email verified! Account created successfully.")
                        return redirect('dashboard')
                    except Exception as e:
                        messages.error(request, f"Registration error: {e}")
                        return redirect('signup')
            attempts = cache.get(att_key, 0) + 1
            cache.set(att_key, attempts, 600)
            if attempts >= 5: cache.set(blk_key, True, 600)
            messages.error(request, translate_text("Invalid or expired OTP.", lang))
            return render(request, 'registration/verify_otp.html', {'current_lang': lang})
        email_hash = request.session.get('reset_email_hash')
        if not email_hash: return redirect('forgot_password')
        att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
        if cache.get(blk_key):
            return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        if user and user.otp == otp_input:
            if (timezone.now() - user.otp_created_at).total_seconds() < 300:
                request.session['otp_verified'] = True
                return redirect('reset_password')
        attempts = cache.get(att_key, 0) + 1
        cache.set(att_key, attempts, 600)
        if attempts >= 5: cache.set(blk_key, True, 600)
        messages.error(request, translate_text("Invalid or expired OTP.", lang))
        return render(request, 'registration/verify_otp.html', {'current_lang': lang})

class ResendOTPView(View):
    def get(self, request):
        lang = request.session.get('lang', 'en')
        if request.session.get('is_signup'):
            signup_data = request.session.get('signup_data')
            if not signup_data: return redirect('signup')
            new_otp = str(random.randint(100000, 999999))
            signup_data['otp'] = new_otp
            signup_data['otp_time'] = timezone.now().timestamp()
            request.session['signup_data'] = signup_data
            dummy_user = CustomUser(username=signup_data['username'])
            dummy_user.set_email(signup_data['email'])
            send_system_email(dummy_user, request, 'otp', extra_context={'otp': new_otp, 'lang': lang})
            messages.success(request, translate_text("New OTP sent.", lang))
            return redirect('verify_otp')
        email_hash = request.session.get('reset_email_hash')
        if not email_hash: return redirect('forgot_password')
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        if not user: return redirect('forgot_password')
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
    if request.user != target_user and active_role in ['admin', 'hod']:
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
    
    # Use your registered Hindi font for the title
    p.setFont("HindiFont", 16)
    p.drawString(50, height - 50, "DPDP Privacy Audit Report")
    
    y = height - 100
    logs = DataAccessLog.objects.all().order_by('-access_time')
    
    for log in logs:
        # Switch to HindiFont here so Hindi names are visible
        p.setFont("HindiFont", 10)
        
        log_text = f"{log.access_time.strftime('%Y-%m-%d')}: {log.accessed_by.username} accessed {log.target_user.username}"
        p.drawString(50, y, log_text)
        
        y -= 20
        if y < 50:
            p.showPage()
            p.setFont("HindiFont", 10) # Reset font on new page
            y = height - 50
    p.setFont("HindiFont", 20)
    p.drawString(100, 100, "रिकी टेस्ट")        
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
    """Unified profile view - displaying QPR office details"""
    lang = request.session.get('lang', 'en')
    user = request.user
    profile = user.profile if hasattr(user, 'profile') else None
    
    # Fetch QPR details
    latest_qpr = QPRRecord.objects.filter(user=user).order_by('-updated_at').first()
    qpr_office_name = ""
    qpr_office_code = ""
    qpr_phone = ""
    qpr_email = ""
    
    if latest_qpr:
        qpr_office_name = latest_qpr.officeName
        qpr_office_code = latest_qpr.officeCode
        qpr_phone = latest_qpr.phone or ""
        qpr_email = latest_qpr.email or ""
    
    if request.method == 'POST':
        new_email = request.POST.get('email', '').lower().strip()
        hod_name = request.POST.get('hod_name', '').strip()
        employee_code = request.POST.get('employee_code', '').strip()
        phone = request.POST.get('phone', '').strip()
        office_code_post = request.POST.get('office_code', '').strip()
        office_name_post = request.POST.get('office_name', '').strip()
        
        # Check if user can edit - either not frozen, edit_allowed, or has approved request
        approved_request = EditRequest.objects.filter(
            user=user,
            request_type='profile',
            status='approved'
        ).first()
        
        can_edit = (not user.is_frozen) or user.is_edit_allowed or (approved_request is not None)
        
        if user.is_frozen and not can_edit:
            messages.error(request, translate_text("Profile is frozen. Request edit permission.", lang), extra_tags='danger')
            return redirect('dashboard')
        
        # Basic validation
        if not new_email:
            messages.error(request, translate_text("Email is required.", lang), extra_tags='danger')
        elif not hod_name:
            messages.error(request, translate_text("HOD selection is required.", lang), extra_tags='danger')
        else:
            # prevent duplicate email across users
            email_hash = hashlib.sha256(new_email.encode()).hexdigest()
            if CustomUser.objects.filter(email_hash=email_hash).exclude(pk=user.pk).exists():
                messages.error(request, translate_text("Email already in use.", lang), extra_tags='danger')
            else:
                # Update encrypted email on user (keeps auth flow)
                user.set_email(new_email)
                if user.is_edit_allowed:
                    user.is_edit_allowed = False
                user.save()

                # Update UserProfile fields from submitted form
                if profile:
                    if employee_code:
                        profile.employee_code = employee_code
                    profile.phone = phone or profile.phone
                    profile.hod_name = hod_name
                    profile.office_code = office_code_post or profile.office_code
                    profile.office_name = office_name_post or profile.office_name
                    profile.email = new_email
                    profile.save()

                # Mark approved request as used
                if approved_request:
                    approved_request.status = 'used'
                    approved_request.save()

                send_system_email(user, request, 'update')
                messages.success(request, translate_text("Profile updated successfully!", lang))
                return redirect('dashboard')
    
    # Get list of available HODs
    available_hods = get_active_hods()
    current_hod = profile.hod_name if profile else None
    
    # Check for approved request
    approved_request = EditRequest.objects.filter(
        user=user,
        request_type='profile',
        status='approved'
    ).first()
    
    # Check for pending/rejected requests
    pending_edit_request = EditRequest.objects.filter(
        user=user,
        request_type='profile',
        status='pending'
    ).first()
    
    rejected_edit_request = EditRequest.objects.filter(
        user=user,
        request_type='profile',
        status='rejected'
    ).order_by('-created_at').first()
    
    context = {
        'profile': profile,
        'available_hods': available_hods,
        'current_hod': current_hod,
        'approved_edit_request': approved_request,
        'pending_edit_request': pending_edit_request,
        'rejected_edit_request': rejected_edit_request,
        'can_edit': (not user.is_frozen) or user.is_edit_allowed or (approved_request is not None),
        'qpr_office_name': qpr_office_name,
        'qpr_office_code': qpr_office_code,
        'qpr_phone': qpr_phone,
        'qpr_email': qpr_email,
    }
    
    return render(request, 'profile.html', context)

@login_required
def user_profile(request):
    """QPR specific profile with office details"""
    lang = request.session.get('lang', 'en')
    profile = request.user.profile
    profile.refresh_from_db()
    profile_submitted = profile.profile_updated
    
    # Fetch QPR details
    latest_qpr = QPRRecord.objects.filter(user=request.user).order_by('-updated_at').first()
    qpr_office_name = ""
    qpr_office_code = ""
    qpr_phone = ""
    qpr_email = ""
    
    if latest_qpr:
        qpr_office_name = latest_qpr.officeName
        qpr_office_code = latest_qpr.officeCode
        qpr_phone = latest_qpr.phone or ""
        qpr_email = latest_qpr.email or ""
    
    # Check for edit requests
    pending_edit_request = EditRequest.objects.filter(
        user=request.user,
        request_type='profile',
        status='pending'
    ).first()
    
    approved_edit_request = EditRequest.objects.filter(
        user=request.user,
        request_type='profile',
        status='approved'
    ).first()
    
    rejected_edit_request = EditRequest.objects.filter(
        user=request.user,
        request_type='profile',
        status='rejected'
    ).order_by('-created_at').first()

    if request.method == 'POST':
        email = request.POST.get('email')
        hod_name = request.POST.get('hod_name', '').strip()
        if not email:
            messages.error(request, translate_text('Email is required', lang))
        elif not hod_name:
            messages.error(request, translate_text('HOD selection is required', lang))
        elif profile_submitted and not approved_edit_request:
            messages.error(request, translate_text('You cannot edit a submitted profile. Please request approval from Admin first.', lang))
        else:
            profile.email = email
            profile.hod_name = hod_name
            profile.profile_updated = True
            profile.save()
            request.user.email = email
            request.user.save()
            
            # Clear approved request after edit
            if approved_edit_request:
                approved_edit_request.delete()
            
            messages.success(request, translate_text('Profile updated successfully! Your profile is now frozen. To edit it again, request approval from admin.', lang))
            return redirect('qpr_user_dashboard')

    # Get list of available HODs for selection
    available_hods = get_active_hods()

    context = {
        'profile': profile,
        'profile_updated': profile.profile_updated,
        'pending_edit_request': pending_edit_request,
        'approved_edit_request': approved_edit_request,
        'rejected_edit_request': rejected_edit_request,
        'can_edit': not profile_submitted or approved_edit_request is not None,
        'available_hods': available_hods,
        'current_hod': profile.hod_name,
        'qpr_office_name': qpr_office_name,
        'qpr_office_code': qpr_office_code,
        'qpr_phone': qpr_phone,
        'qpr_email': qpr_email,
    }
    response = render(request, 'profile.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

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
    
    # Check if already pending
    pending_request = EditRequest.objects.filter(
        user=request.user,
        request_type='profile',
        status='pending'
    ).exists()
    
    if pending_request:
        messages.warning(request, translate_text("You already have a pending profile edit request.", lang))
    else:
        # Try to find the user's manager/HOD and send the request there so manager can unlock
        profile = getattr(request.user, 'profile', None)
        hod_name = profile.hod_name if profile else None
        manager_user = None
        if hod_name:
            # Try to locate a CustomUser whose profile.hod_name or profile.name matches
            manager_user = CustomUser.objects.filter(profile__hod_name__iexact=hod_name).first()
            if not manager_user:
                manager_user = CustomUser.objects.filter(profile__name__iexact=hod_name).first()

        if manager_user:
            ManagerRequest.objects.create(
                hod=manager_user,
                user=request.user,
                request_type='profile',
                reason='User requested permission to edit frozen profile',
                status='pending'
            )
            messages.success(request, translate_text("Profile edit request sent to your manager for approval.", lang))
            # Notify manager
            msg = f"User {user.username} has requested permission to edit their profile."
            send_system_email(manager_user, request, 'manager_alert', extra_context={'body_text': msg})
        else:
            # Fallback to admin approval if no manager found
            EditRequest.objects.create(
                user=request.user,
                request_type='profile',
                requested_data={'reason': 'User requested permission to edit profile'},
                reason='User requested permission to edit frozen profile',
                status='pending'
            )
            messages.success(request, translate_text("Profile edit request sent to admin for approval.", lang))
            admin = CustomUser.objects.filter(role='admin').first()
            if admin:
                msg = f"User {user.username} has requested permission to edit their profile."
                send_system_email(admin, request, 'manager_alert', extra_context={'body_text': msg})
    
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
    profile.refresh_from_db()
    qpr_records = QPRRecord.objects.filter(user=request.user)
    submitted_qprs = qpr_records.filter(is_submitted=True).count()
    context = {
        'profile': profile,
        'profile_status': 'Updated' if profile.profile_updated else 'Needs Update',
        'qpr_submitted': submitted_qprs > 0, 
        'qpr_count': qpr_records.count(),
        'user': request.user
    }
    response = render(request, 'dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response 
@login_required
@login_required
def qpr_hod_dashboard(request):
    """HOD Dashboard - Department overview and employee statistics"""
    if request.user.profile.role != 'hod': return redirect('/')
    lang = request.session.get('lang', 'en')
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
        'hod_name': hod_name,
        'current_lang': lang
    }
    response = render(request, 'qpr/hod_dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response 

@login_required
def manager_dashboard(request):
    """Manager Dashboard - Manage system access and employee records"""
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

    # Pending profile edit requests targeted to this manager
    pending_profile_requests = ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='pending')
    context = {
        'users': users, 
        'employees': employee_data,
        'pending_profile_requests': pending_profile_requests,
    }
    return render(request, 'manager_dashboard.html', context)

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
            
            # Mark any pending ManagerRequest for this user as approved
            ManagerRequest.objects.filter(user=target_user, request_type='profile', status='pending').update(status='approved')

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
    
    # --- ACTIVE USERS ---
    users = CustomUser.objects.filter(is_active=True, is_archived=False).order_by('-date_joined')
    
    # --- ARCHIVED USERS ---
    archived_users = ArchivedUser.objects.all().order_by('-archived_at')
    
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
    context = {
        'hod_stats': hod_stats, 
        'manager_requests': pending_requests,
        'users': users,
        'archived_users': archived_users
    }
    response = render(request, 'dashboard.html', context) # Renders UNIFIED DASHBOARD
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

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
    quarter_filter = request.GET.get('quarter', '').strip()
    year_filter = request.GET.get('year', '').strip()
    
    hods = UserProfile.objects.filter(role='hod').order_by('name')
    hod_groups = []
    
    # Collect all unique quarters and years for filter dropdowns
    all_qpr_records = QPRRecord.objects.all()
    all_quarters = sorted(set(all_qpr_records.values_list('quarter', flat=True).filter(quarter__isnull=False)))
    all_years = sorted(set(all_qpr_records.values_list('year', flat=True).filter(year__isnull=False)), reverse=True)
    
    for hod_profile in hods:
        users_under_hod = UserProfile.objects.filter(role='user', hod_name=hod_profile.hod_name).order_by('name')
        user_details = []
        for user_profile in users_under_hod:
            if employee_code_filter and employee_code_filter.lower() not in user_profile.employee_code.lower(): continue
            user_name = user_profile.name or user_profile.user.get_full_name() or user_profile.user.username
            if name_filter and name_filter.lower() not in user_name.lower(): continue
            qpr_records = QPRRecord.objects.filter(user=user_profile.user).order_by('-id')
            latest_qpr = qpr_records.first() if qpr_records else None
            
            # Apply quarter and year filters
            if quarter_filter and latest_qpr and latest_qpr.quarter != quarter_filter: continue
            if year_filter and latest_qpr and latest_qpr.year != year_filter: continue
            
            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_name,
                'email': user_profile.user.email,
                'office_name': user_profile.office_name or (latest_qpr.officeName if latest_qpr else 'Not Set'),
                'office_code': user_profile.office_code or (latest_qpr.officeCode if latest_qpr else 'Not Set'),
                'quarter': latest_qpr.quarter if latest_qpr else 'N/A',
                'year': latest_qpr.year if latest_qpr else 'N/A',
                'qpr_status': latest_qpr.status if latest_qpr else 'Not Submitted',
            })
        if user_details:
            hod_groups.append({
                'hod_name': hod_profile.hod_name, 
                'hod_email': hod_profile.user.email,
                'hod_emp_code': hod_profile.employee_code,
                'user_count': len(user_details), 
                'users': user_details
            })
    
    context = {
        'hod_groups': hod_groups,
        'all_quarters': all_quarters,
        'all_years': all_years,
        'quarter_filter': quarter_filter,
        'year_filter': year_filter,
        'employee_code_filter': employee_code_filter,
        'name_filter': name_filter,
    }
    return render(request, 'qpr/admin_employee_list.html', context)

@user_passes_test(lambda u: u.role in ['hod', 'admin'])
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

@user_passes_test(lambda u: u.is_authenticated and (u.role in ['hod', 'admin'] or u.is_superuser))
def manage_user_action(request, user_id, action):
    """Restored Full Action Logic: Archive, Unarchive, Unlock

    This handler accepts either a user id (for user-level actions) or a QPR id
    for the special-case action 'unlock_qpr'. We handle 'unlock_qpr' first to
    avoid attempting to resolve a CustomUser for a QPR id (which caused 404s).
    """
    # Special-case: treat provided id as QPR id when unlocking a QPR
    if action == 'unlock_qpr':
        if not (request.user.role in ['manager', 'admin'] or request.user.is_superuser):
            messages.error(request, translate_text("Unauthorized", request.session.get('lang', 'en')))
            return redirect('manager_dashboard')
        try:
            qpr = QPRRecord.objects.get(id=user_id)
            qpr.is_submitted = False
            qpr.status = 'Draft'
            qpr.save()
            messages.success(request, translate_text("QPR Form unlocked successfully.", request.session.get('lang', 'en')))
        except QPRRecord.DoesNotExist:
            messages.error(request, translate_text("QPR Record not found.", request.session.get('lang', 'en')))
        return redirect('manager_dashboard')

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
    # Prefill QPR form with user's profile values when present (read-only in form)
    profile = getattr(request.user, 'profile', None)
    profile_office_name = profile.office_name if profile and profile.office_name else ''
    profile_office_code = profile.office_code if profile and profile.office_code else ''
    profile_phone = profile.phone if profile and profile.phone else ''
    profile_email = profile.email if profile and profile.email else (request.user.get_email() if hasattr(request.user, 'get_email') else '')

    # Build a list of already used quarters for this user (quarter, year, record_id)
    used = []
    for r in QPRRecord.objects.filter(user=request.user):
        used.append({'quarter': r.quarter, 'year': r.year or '', 'record_id': r.id})

    context = {
        'profile_office_name': profile_office_name,
        'profile_office_code': profile_office_code,
        'profile_phone': profile_phone,
        'profile_email': profile_email,
        'profile_office_name_filled': bool(profile_office_name),
        'profile_office_code_filled': bool(profile_office_code),
        'profile_phone_filled': bool(profile_phone),
        'profile_email_filled': bool(profile_email),
        'used_quarters_json': json.dumps(used),
    }
    return render(request, 'qpr/qpr_form.html', context)

@login_required
def report_list(request):
    return render(request, 'qpr/report_list.html')
@login_required
def report_detail(request, record_id):
    return render(request, 'qpr/report_detail.html', {'record_id': record_id})

@login_required
def typing_usage_report_form(request, record_id):
    """Display form for typing usage report"""
    qpr_record = get_object_or_404(QPRRecord, id=record_id, user=request.user)
    
    if request.method == 'POST':
        form = TypingUsageReportForm(request.POST)
        if form.is_valid():
            total_words = form.cleaned_data['total_words']
            hindi_words = form.cleaned_data['hindi_words']
            
            # Create or update the typing usage report
            report, created = TypingUsageReport.objects.update_or_create(
                qpr_record=qpr_record,
                defaults={'total_words': total_words, 'hindi_words': hindi_words}
            )
            
            return redirect('typing_usage_report_view', record_id=record_id)
    else:
        # Pre-fill form if report exists
        try:
            report = TypingUsageReport.objects.get(qpr_record=qpr_record)
            form = TypingUsageReportForm(initial={
                'total_words': report.total_words,
                'hindi_words': report.hindi_words
            })
        except TypingUsageReport.DoesNotExist:
            form = TypingUsageReportForm()
    
    context = {
        'form': form,
        'record_id': record_id,
        'office_name': qpr_record.officeName
    }
    return render(request, 'qpr/typing_usage_report.html', context)

@login_required
def typing_usage_report_view(request, record_id):
    """Display typing usage report with details"""
    qpr_record = get_object_or_404(QPRRecord, id=record_id, user=request.user)
    
    # Get employee profile
    user_profile = request.user.profile
    employee_name = user_profile.name or request.user.username
    designation = user_profile.office_name  # Or you can get it from Employee model
    
    # Try to get designation from Employee model if available
    try:
        employee = Employee.objects.get(empcode=user_profile.employee_code)
        designation = employee.designation or designation
    except Employee.DoesNotExist:
        pass
    
    # Get section7 data (notings data)
    try:
        section7 = qpr_record.section7
        total_notes = section7.total_pages or 0
        hindi_notes = section7.hindi_pages or 0
    except:
        total_notes = 0
        hindi_notes = 0
    
    # Get typing usage report data
    try:
        typing_report = TypingUsageReport.objects.get(qpr_record=qpr_record)
        total_words = typing_report.total_words or 0
        hindi_words = typing_report.hindi_words or 0
    except TypingUsageReport.DoesNotExist:
        total_words = 0
        hindi_words = 0
    
    # Calculate percentages
    notes_hindi_percentage = (hindi_notes / total_notes * 100) if total_notes > 0 else 0
    words_hindi_percentage = (hindi_words / total_words * 100) if total_words > 0 else 0
    
    context = {
        'record_id': record_id,
        'office_name': qpr_record.officeName,
        'employee_name': employee_name,
        'designation': designation,
        'total_notes': total_notes,
        'hindi_notes': hindi_notes,
        'notes_hindi_percentage': round(notes_hindi_percentage, 2),
        'total_words': total_words,
        'hindi_words': hindi_words,
        'words_hindi_percentage': round(words_hindi_percentage, 2),
    }
    
    return render(request, 'qpr/typing_usage_report_view.html', context)

@login_required
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
    response = render(request, 'qpr/hod_detail_list.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

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
                # Check for approved ManagerRequest targeted to this user (manager approved)
                # Also respect the user's is_edit_allowed flag (set when manager unlocks)
                edit_approved = (
                    ManagerRequest.objects.filter(user=request.user, request_type='qpr', status='approved').exists()
                    or bool(getattr(request.user, 'is_edit_allowed', False))
                )
                # Also allow explicit approved EditRequest entries
                if not edit_approved:
                    edit_approved = EditRequest.objects.filter(
                        user=request.user,
                        request_type='qpr',
                        qpr_record_id=record.id,
                        status='approved'
                    ).exists()
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
                # If manager temporarily allowed edits, revoke after this save
                if getattr(request.user, 'is_edit_allowed', False):
                    request.user.is_edit_allowed = False
                    request.user.save(update_fields=['is_edit_allowed'])
                if record.is_submitted:
                    ManagerRequest.objects.filter(hod=request.user, request_type='qpr', status='approved').delete()
                    # Mark approved EditRequest as used
                    approved_edit_request = EditRequest.objects.filter(
                        user=request.user,
                        request_type='qpr',
                        qpr_record_id=record.id,
                        status='approved'
                    ).first()
                    if approved_edit_request:
                        approved_edit_request.status = 'used'
                        approved_edit_request.save()
                _save_section_data(record, details)
            else:
                # Enforce one record per user per quarter+year. If a record already
                # exists for this user and quarter/year, disallow creating another
                # and instruct the user to request edit instead.
                quarter = data.get('quarter', '').strip()
                year = data.get('year', '').strip() or None
                if quarter:
                    exists = QPRRecord.objects.filter(user=request.user, quarter=quarter)
                    if year:
                        exists = exists.filter(year=year)
                    if exists.exists():
                        return JsonResponse({'error': 'A report for this quarter already exists. To change it, request edit permission.'}, status=400)

                is_submitted = (data.get('status', 'Draft') == 'Submitted')
                record = QPRRecord.objects.create(
                    user=request.user, officeName=data.get('officeName', ''), officeCode=data.get('officeCode', ''),
                    region=data.get('region', ''), quarter=data.get('quarter', ''), year=data.get('year', ''), status=data.get('status', 'Draft'),
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
        # Compute edit approval flags consistent with api_records
        edit_approved = False
        if record.is_submitted:
            edit_approved = (
                ManagerRequest.objects.filter(user=request.user, request_type='qpr', status='approved').exists()
                or bool(getattr(request.user, 'is_edit_allowed', False))
            )
            if not edit_approved:
                edit_approved = EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record.id,
                    status='approved'
                ).exists()
        data['can_edit'] = not record.is_submitted or edit_approved
        data['edit_approved'] = edit_approved
        return JsonResponse(data, safe=False)
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Record not found'}, status=404)


@login_required
def print_qpr_report(request, record_id):
    """Render a server-side printable version of the QPR record (matches view)."""
    try:
        record = QPRRecord.objects.get(pk=record_id, user=request.user)
    except QPRRecord.DoesNotExist:
        return redirect('qpr_report_list')

    data = serialize_qpr_record(record)
    # Render server-side template with the same fields used by report_detail
    return render(request, 'qpr/print_report.html', {'r': data})

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
            #if not admin_users.exists(): return JsonResponse({'success': False, 'error': 'No Admin found'}, status=400)
            for admin_user in admin_users:
                ManagerRequest.objects.create(hod=request.user, user=admin_user, request_type=request_type, reason=f"Edit request: {reason}")
            return JsonResponse({'success': True, 'message': 'Request sent'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=400)

class EmployeeListCreateAPI(APIView):
    def get(self, request):
        if request.session.get('active_role') != 'user':
            return Response({"detail": "Unauthorized"}, status=403)

        try:
            user_empcode = int(request.user.username)
        except ValueError:
            return Response({"detail": "Invalid employee code."}, status=400)

        status_filter = request.GET.get("status")

        qs = Employee.objects.filter(empcode=user_empcode)

        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = EmployeeSerializer(qs.order_by("-lastupdate"), many=True)
        return Response(serializer.data)
    def post(self, request):
        if request.session.get('active_role') != 'user':
            return Response({"detail": "Unauthorized"}, status=403)

        try:
            user_empcode = int(request.user.username)
        except ValueError:
            return Response({"detail": "Username must be numeric."}, status=400)

        # Allow only one record
        if Employee.objects.filter(empcode=user_empcode).exists():
            return Response(
                {"detail": "You have already created your employee record."},
                status=400
            )

        data = request.data.copy()
        data["empcode"] = user_empcode

        serializer = EmployeeSerializer(data=data)

        if serializer.is_valid():
            serializer.save(lastupdate=timezone.now())
            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)

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
        if not emp:
            return Response({"error": "Not found"}, status=404)

        # USER cannot edit others
        if request.user.role == 'user' and str(emp.empcode) != str(request.user.username):
            return Response({"error": "Unauthorized"}, status=403)
        if str(emp.empcode) != str(request.user.username):
            return Response({"detail": "Unauthorized"}, status=403)

        serializer = EmployeeSerializer(emp, data=request.data)

        if serializer.is_valid():
            serializer.save(lastupdate=timezone.now())
            return Response(serializer.data)

        return Response(serializer.errors, status=400)
    def delete(self, request, pk):
        emp = self.get_object(pk)
        if str(emp.empcode) != str(request.user.username):
            return Response({"detail": "Unauthorized"}, status=403)
        if not emp:
            return Response({"error": "Not found"}, status=404)

        if request.user.role == 'user' and str(emp.empcode) != str(request.user.username):
            return Response({"error": "Unauthorized"}, status=403)

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


# ==================== EDIT REQUEST WORKFLOW ====================

@login_required
def request_profile_edit(request):
    """User requests to edit their profile"""
    lang = request.session.get('lang', 'en')
    
    if request.method == 'POST':
        try:
            # Check if already pending
            pending_request = EditRequest.objects.filter(
                user=request.user,
                request_type='profile',
                status='pending'
            ).first()
            
            if pending_request:
                messages.warning(request, translate_text("You already have a pending profile edit request. Please wait for approval.", lang))
                return redirect('qpr_user_profile')
            
            reason = request.POST.get('reason', '')
            profile_data = {
                'email': request.POST.get('email', ''),
                'name': request.POST.get('name', ''),
                'office_name': request.POST.get('office_name', ''),
                'office_code': request.POST.get('office_code', ''),
            }
            
            EditRequest.objects.create(
                user=request.user,
                request_type='profile',
                requested_data=profile_data,
                reason=reason,
                status='pending'
            )
            messages.success(request, translate_text("Profile edit request submitted to admin for approval. You will not be able to submit again until approved or rejected.", lang))
            
            # Send notification to admins
            admins = CustomUser.objects.filter(role='admin', is_active=True)
            for admin in admins:
                msg = f"User {request.user.username} ({request.user.profile.employee_code}) has requested to edit their profile."
                send_system_email(admin, request, 'manager_alert', extra_context={'body_text': msg})
            
            return redirect('qpr_user_profile')
        except Exception as e:
            messages.error(request, translate_text("Error submitting request.", lang))
            return redirect('qpr_user_profile')
    
    context = {'profile': request.user.profile, 'current_lang': lang}
    return render(request, 'qpr/request_profile_edit.html', context)


@login_required
def request_qpr_edit(request, record_id):
    """User requests to edit their submitted QPR"""
    lang = request.session.get('lang', 'en')
    
    try:
        qpr_record = QPRRecord.objects.get(id=record_id, user=request.user)
    except QPRRecord.DoesNotExist:
        messages.error(request, translate_text("QPR record not found.", lang))
        return redirect('qpr_report_list')
    
    if request.method == 'POST':
        try:
            reason = request.POST.get('reason', '')
            
            # Check if already pending
            pending_request = EditRequest.objects.filter(
                user=request.user,
                request_type='qpr',
                qpr_record_id=record_id,
                status='pending'
            ).exists()
            
            if pending_request:
                messages.warning(request, translate_text("You already have a pending QPR edit request for this record.", lang))
            else:
                qpr_data = {
                    'qpr_id': record_id,
                    'office_name': qpr_record.officeName,
                    'quarter': qpr_record.quarter,
                    'year': qpr_record.year,
                }
                
                EditRequest.objects.create(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    requested_data=qpr_data,
                    reason=reason,
                    status='pending'
                )
                messages.success(request, translate_text("QPR edit request submitted to admin for approval.", lang))
                
                # Send notification to admins
                admins = CustomUser.objects.filter(role='admin', is_active=True)
                for admin in admins:
                    msg = f"User {request.user.username} ({request.user.profile.employee_code}) has requested to edit QPR for {qpr_record.quarter}."
                    send_system_email(admin, request, 'manager_alert', extra_context={'body_text': msg})
            
            return redirect('qpr_report_detail', record_id=record_id)
        except Exception as e:
            messages.error(request, translate_text("Error submitting request.", lang))
            return redirect('qpr_report_detail', record_id=record_id)
    
    context = {'qpr_record': qpr_record, 'current_lang': lang}
    return render(request, 'qpr/request_qpr_edit.html', context)


@login_required
def admin_edit_requests(request):
    """Admin view all pending edit requests"""
    if request.user.role != 'admin':
        return redirect('/')
    lang = request.session.get('lang', 'en')
    
    status_filter = request.GET.get('status', 'pending')
    request_type_filter = request.GET.get('type', '')
    
    edit_requests = EditRequest.objects.select_related('user', 'approved_by').all()
    
    if status_filter:
        edit_requests = edit_requests.filter(status=status_filter)
    
    if request_type_filter:
        edit_requests = edit_requests.filter(request_type=request_type_filter)
    
    context = {
        'edit_requests': edit_requests,
        'status_filter': status_filter,
        'request_type_filter': request_type_filter,
        'statuses': [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('used', 'Used')],
        'types': [('profile', 'Profile'), ('qpr', 'QPR')],
        'current_lang': lang,
    }
    return render(request, 'qpr/admin_edit_requests.html', context)


@login_required
def approve_edit_request(request, request_id):
    """Manager/Admin approves an edit request"""
    if request.user.role not in ['manager', 'admin']:
        return redirect('/')
    lang = request.session.get('lang', 'en')
    
    try:
        edit_request = EditRequest.objects.get(id=request_id)
    except EditRequest.DoesNotExist:
        messages.error(request, translate_text("Request not found.", lang))
        return redirect('admin_edit_requests')
    
    if request.method == 'POST':
        try:
            admin_notes = request.POST.get('admin_notes', '')
            
            edit_request.status = 'approved'
            edit_request.approved_by = request.user
            edit_request.approved_at = now()
            edit_request.admin_notes = admin_notes
            edit_request.save()
            
            # Send notification to user
            msg = f"Your {edit_request.get_request_type_display().lower()} edit request has been approved."
            if admin_notes:
                msg += f"\n\nAdmin Notes: {admin_notes}"
            send_system_email(
                edit_request.user,
                request,
                'manager_alert',
                extra_context={'body_text': msg, 'subject': 'Edit Request Approved'}
            )
            
            messages.success(request, translate_text("Edit request approved.", lang))
            if request.user.role == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
        except Exception as e:
            messages.error(request, translate_text(f"Error approving request: {str(e)}", lang))
            if request.user.role == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
    
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/approve_edit_request.html', context)


@login_required
def reject_edit_request(request, request_id):
    """Manager/Admin rejects an edit request"""
    if request.user.role not in ['manager', 'admin']:
        return redirect('/')
    lang = request.session.get('lang', 'en')
    
    try:
        edit_request = EditRequest.objects.get(id=request_id)
    except EditRequest.DoesNotExist:
        messages.error(request, translate_text("Request not found.", lang))
        return redirect('admin_edit_requests')
    
    if request.method == 'POST':
        try:
            admin_notes = request.POST.get('admin_notes', '')
            
            if not admin_notes:
                messages.error(request, translate_text("Please provide a reason for rejection.", lang))
                return render(request, 'qpr/reject_edit_request.html', {'edit_request': edit_request})
            
            edit_request.status = 'rejected'
            edit_request.approved_by = request.user
            edit_request.approved_at = now()
            edit_request.admin_notes = admin_notes
            edit_request.save()
            
            # Send notification to user
            msg = f"Your {edit_request.get_request_type_display().lower()} edit request has been rejected.\n\nReason: {admin_notes}"
            send_system_email(
                edit_request.user,
                request,
                'manager_alert',
                extra_context={'body_text': msg, 'subject': 'Edit Request Rejected'}
            )
            
            messages.success(request, translate_text("Edit request rejected.", lang))
            if request.user.role == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
        except Exception as e:
            messages.error(request, translate_text(f"Error rejecting request: {str(e)}", lang))
            if request.user.role == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
    
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/reject_edit_request.html', context)


@login_required
@user_passes_test(is_admin)
def typing_data_report(request):
    """Admin view all employees' typing usage data"""
    lang = request.session.get('lang', 'en')
    
    # Get all typing usage reports with related data
    typing_reports = TypingUsageReport.objects.select_related(
        'qpr_record__user__profile',
        'qpr_record__section7'
    ).all()
    
    data = []
    for report in typing_reports:
        qpr_record = report.qpr_record
        user_profile = qpr_record.user.profile
        
        # Get employee name
        employee_name = user_profile.name or qpr_record.user.username
        
        # Get designation
        designation = user_profile.office_name or 'N/A'
        try:
            employee = Employee.objects.get(empcode=user_profile.employee_code)
            designation = employee.designation or designation
        except Employee.DoesNotExist:
            pass
        
        # Get section7 data
        try:
            section7 = qpr_record.section7
            total_notes = section7.total_pages or 0
            hindi_notes = section7.hindi_pages or 0
        except:
            total_notes = 0
            hindi_notes = 0
        
        # Calculate percentages
        notes_hindi_percentage = (hindi_notes / total_notes * 100) if total_notes > 0 else 0
        words_hindi_percentage = (report.hindi_words / report.total_words * 100) if report.total_words and report.total_words > 0 else 0
        
        data.append({
            'serial_no': len(data) + 1,
            'employee_name': employee_name,
            'designation': designation,
            'total_notes': total_notes,
            'hindi_notes': hindi_notes,
            'notes_hindi_percentage': round(notes_hindi_percentage, 2),
            'total_words': report.total_words or 0,
            'hindi_words': report.hindi_words or 0,
            'words_hindi_percentage': round(words_hindi_percentage, 2),
        })
    
    context = {
        'typing_data': data,
        'current_lang': lang,
    }
    return render(request, 'qpr/typing_data_report.html', context)


# ==================== HOD MANAGEMENT (ADMIN ONLY) ====================

@csrf_exempt
@login_required
def api_update_hod(request):
    """API endpoint to update HOD name and employee code (Admin only)"""
    if request.user.role != 'admin':
        return JsonResponse({'success': False, 'error': 'Access denied. Admin only.'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            old_hod_name = data.get('old_hod_name')  # Current HOD name
            new_hod_name = data.get('new_hod_name')  # New HOD name
            old_employee_code = data.get('old_employee_code')  # Current HOD employee code
            new_employee_code = data.get('new_employee_code')  # New HOD employee code
            
            if not old_hod_name or not new_hod_name or not old_employee_code or not new_employee_code:
                return JsonResponse({
                    'success': False,
                    'error': 'All fields required: old_hod_name, new_hod_name, old_employee_code, new_employee_code'
                }, status=400)
            
            # Find the HOD user profile
            try:
                hod_profile = UserProfile.objects.get(employee_code=old_employee_code, role='hod')
            except UserProfile.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'HOD with employee code {old_employee_code} not found'
                }, status=404)
            
            # Check if new_employee_code is already taken
            if new_employee_code != old_employee_code:
                if UserProfile.objects.filter(employee_code=new_employee_code).exists():
                    return JsonResponse({
                        'success': False,
                        'error': f'Employee code {new_employee_code} is already in use'
                    }, status=400)
            
            # Update HOD profile
            hod_profile.name = new_hod_name
            hod_profile.hod_name = new_hod_name
            hod_profile.employee_code = new_employee_code
            hod_profile.user.username = new_employee_code  # Update Django User username
            hod_profile.user.save()
            hod_profile.save()
            
            # Update all users under this HOD (update their hod_name reference)
            UserProfile.objects.filter(
                role='user',
                hod_name__iexact=old_hod_name
            ).update(hod_name=new_hod_name)
            
            return JsonResponse({
                'success': True,
                'message': f'HOD updated successfully! {old_hod_name} → {new_hod_name}, {old_employee_code} → {new_employee_code}',
                'new_hod_name': new_hod_name
            })
        
        except Exception as e:
            print(f"ERROR updating HOD: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=400)
def send_reminder_email(request, user_id):
    if request.user.profile.role != 'hod': 
        return redirect('/')
        
    if request.method == 'POST':
        target_user = get_object_or_404(CustomUser, id=user_id)
        lang = request.session.get('lang', 'en')
        if target_user.profile.hod_name == request.user.profile.hod_name:
            send_system_email(target_user, request, 'reminder')
            messages.success(request, translate_text(f"Reminder email sent successfully to {target_user.username}.", lang))
        else:
            messages.error(request, translate_text("Unauthorized action.", lang))
            
    return redirect('qpr_hod_detail_list')
@login_required
def export_employee_pdf(request):
    if request.session.get('active_role') != 'user':
        return redirect('dashboard')

    try:
        user_empcode = int(request.user.username)
    except ValueError:
        messages.error(request, "Invalid employee code.")
        return redirect('dashboard')

    employees = Employee.objects.filter(empcode=user_empcode, status='submitted')
    lang = request.GET.get('lang', 'en')

    # Translation dictionary (same as your JS dictionary)
    hindi_dict = {
        "Passed": "उत्तीर्ण",
        "Did not Appear": "उपस्थित नहीं हुए",
        "Failed": "अनुत्तीर्ण",
        "Good": "अच्छा",
        "Average": "औसत",
        "Basic": "बुनियादी",
        "Hindi": "हिंदी",
        "English": "अंग्रेजी",
        "Both": "दोनों",
        "Gazetted": "राजपत्रित",
        "Non-Gazetted": "अराजपत्रित",
        "Scientist-F": "वैज्ञानिक-एफ",
        "Scientist-G": "वैज्ञानिक-जी",
        "Scientist-E": "वैज्ञानिक-ई",
        "Scientist-D": "वैज्ञानिक-डी",
        "Scientist-C": "वैज्ञानिक-सी",
        "Scientist-B": "वैज्ञानिक-बी",
        "Section Officer": "अनुभाग अधिकारी",
        "Senior Secretariate Assistant": "वरिष्ठ सचिवालय सहायक",
        "Scientific/Technical Assistant-A": "वैज्ञानिक/तकनीकी सहायक-ए",
        "Scientific/Technical Assistant-B": "वैज्ञानिक/तकनीकी सहायक-बी",
        "Scientific Officer/Engineer-SB": "वैज्ञानिक अधिकारी/इंजीनियर-एसबी",
        "Pending": "लंबित",
    }

    def t(value):
        """Translate value if lang is Hindi"""
        if not value or value == '-':
            return '-'
        if lang == 'hi':
            return hindi_dict.get(str(value), str(value))
        return str(value)

    buffer = io.BytesIO()

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    page = landscape(A4)
    margin = 15 * mm

    doc = SimpleDocTemplate(
        buffer, pagesize=page,
        rightMargin=margin, leftMargin=margin,
        topMargin=margin, bottomMargin=margin
    )

    header_style = ParagraphStyle('Header', fontName='HindiFont', fontSize=8,
        leading=11, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle('Cell', fontName='HindiFont', fontSize=8,
        leading=11, alignment=1)
    title_style = ParagraphStyle('Title', fontName='HindiFont', fontSize=14,
        leading=18, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', fontName='HindiFont', fontSize=9,
        leading=12, spaceAfter=10, textColor=colors.HexColor('#555555'))

    col_widths = [18*mm, 28*mm, 28*mm, 38*mm, 18*mm, 22*mm, 22*mm, 20*mm, 20*mm, 18*mm, 20*mm, 17*mm]

    # Headers — translated if Hindi
    if lang == 'hi':
        header_texts = [
            "एम्पकोड", "अंग्रेजी में नाम", "हिंदी में नाम", "पद का नाम",
            "टाइपिंग", "हिंदी<br/>प्रवीणता", "राजपत्र", "प्रबोध",
            "प्रवीण", "प्रज्ञा", "पारंगत", "सेवानिवृत्ति<br/>तिथि"
        ]
        title_text = "सबमिट किए गए कर्मचारी रिकॉर्ड"
    else:
        header_texts = [
            "Emp<br/>Code", "Name in<br/>English", "Name in<br/>Hindi", "Designation",
            "Typing", "Hindi<br/>Proficiency", "Gazet", "Prabodh",
            "Praveen", "Pragya", "Parangat", "Superann.<br/>Date"
        ]
        title_text = "Submitted Employee Records"

    headers = [Paragraph(h, header_style) for h in header_texts]
    table_data = [headers]

    for emp in employees:
        raw_date = emp.get_super_annuation_date()
        masked_date = f"**-**-{raw_date.year}" if raw_date else "-"

        row = [
            Paragraph(str(emp.empcode or '-'), cell_style),
            Paragraph(str(emp.ename or '-'), cell_style),
            Paragraph(str(emp.hname or '-'), cell_style),
            Paragraph(t(emp.designation), cell_style),
            Paragraph(t(emp.typing), cell_style),
            Paragraph(t(emp.hindiproficiency), cell_style),
            Paragraph(t(emp.gazet), cell_style),
            Paragraph(t(emp.prabodh), cell_style),
            Paragraph(t(emp.praveen), cell_style),
            Paragraph(t(emp.pragya), cell_style),
            Paragraph(t(emp.parangat), cell_style),
            Paragraph(masked_date, cell_style),
        ]
        table_data.append(row)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a6496')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'HindiFont'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a6496')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f6fb')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    from datetime import date
    elements = [
        Paragraph(title_text, title_style),
        Paragraph(f"Generated on: {date.today().strftime('%d %B %Y')}", subtitle_style),
        Spacer(1, 4*mm),
        table,
    ]

    doc.build(elements)
    buffer.seek(0)
<<<<<<< HEAD
    return FileResponse(buffer, as_attachment=True, filename='employee_records.pdf')
=======
    return FileResponse(buffer, as_attachment=True, filename='employee_records.pdf')


@login_required
def manager_report(request):
    """Manager Report - Display status of last 4 quarterly progress reports"""
    if not (request.user.role in ['manager', 'admin'] or request.user.is_superuser):
        return redirect('/')
    
    # Get the manager's office code from their associated QPRRecords or default
    # For now, we'll get all unique office codes from QPRRecords
    # If manager is associated with specific office, filter accordingly
    manager_user = request.user
    
    # Determine manager's office_code from profile
    manager_office = getattr(request.user.profile, 'office_code', None)
    if not manager_office:
        # fallback: derive from any QPRRecord for this user
        first = QPRRecord.objects.filter(user=request.user).first()
        manager_office = first.officeCode if first else None

    # Get users count for this office (role 'user')
    users_count = 0
    if manager_office:
        users_count = UserProfile.objects.filter(office_code=manager_office, role='user').count()

    # Find quarter-year groups for which number of distinct submitted user records == users_count
    report_data = []
    if manager_office and users_count > 0:
        q_groups = QPRRecord.objects.filter(officeCode=manager_office, is_submitted=True) \
            .values('year', 'quarter') \
            .annotate(submitted_users=Count('user', distinct=True)) \
            .order_by('-year', '-quarter')

        for g in q_groups:
            if g['submitted_users'] >= users_count:
                # pick a representative record to show status_date
                rep = QPRRecord.objects.filter(officeCode=manager_office, year=g['year'], quarter=g['quarter'], is_submitted=True).order_by('-updated_at').first()
                status_date = rep.updated_at.strftime('%b %d, %Y – %I:%M %p') if rep and rep.updated_at else ''
                report_data.append({
                    'year': g['year'] or '2025–2026',
                    'quarter': g['quarter'] or 'Q1',
                    'office_name': rep.officeName if rep else manager_office,
                    'status_title': 'Received by Official Language Department',
                    'status_date': status_date,
                })

    context = {
        'office_code': manager_office or '',
        'qpr_reports': report_data,
    }
    
    return render(request, 'qpr/manager_report.html', context)


@login_required
def manager_report_detail(request, year, quarter):
    """Show list of users who submitted for given quarter and year, grouped by HOD."""
    if not (request.user.role in ['manager', 'admin'] or request.user.is_superuser):
        return redirect('/')

    manager_office = getattr(request.user.profile, 'office_code', None)
    if not manager_office:
        first = QPRRecord.objects.filter(user=request.user).first()
        manager_office = first.officeCode if first else None

    if not manager_office:
        return redirect('manager_report')

    users_qs = UserProfile.objects.filter(office_code=manager_office, role='user').select_related('user').order_by('hod_name', 'name')
    total_users = users_qs.count()

    submitted = QPRRecord.objects.filter(officeCode=manager_office, year=year, quarter=quarter, is_submitted=True)
    submitted_users_count = submitted.values('user').distinct().count()

    # Only allow detail view when all users have submitted
    if submitted_users_count < total_users:
        return redirect('manager_report')

    # Build grouping by HOD
    grouped = {}
    for up in users_qs:
        hod = up.hod_name or 'Unassigned'
        grouped.setdefault(hod, [])

    # Map submitted records by user id
    submitted_map = {r.user_id: r for r in submitted}

    for up in users_qs:
        user = up.user
        if user.id in submitted_map:
            rec = submitted_map[user.id]
            grouped.setdefault(up.hod_name or 'Unassigned', []).append({
                'name': up.name or user.username,
                'empcode': up.employee_code,
                'email': up.email or '',
                'submitted_at': rec.updated_at,
            })

    context = {
        'year': year,
        'quarter': quarter,
        'office_code': manager_office,
        'grouped': grouped,
    }
<<<<<<< HEAD
    return render(request, 'qpr/manager_report_detail.html', context)
>>>>>>> 0615d7b (Apply stashed changes and resolve conflict)
=======
    return render(request, 'qpr/manager_report_detail.html', context)
>>>>>>> 388e46b (changes in print to pdf)
