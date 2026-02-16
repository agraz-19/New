import os  
import io
import csv
import random
import hashlib
import json
from django.utils.timezone import now

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout, get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from django.core.cache import cache
from django.utils import timezone
from django.urls import reverse
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from gtts import gTTS
from captcha.models import CaptchaStore
from deep_translator import GoogleTranslator
from .models import Employee, CustomUser, DataAccessLog, ArchivedUser, cipher_suite
from .forms import CustomLoginForm, CustomUserCreationForm
from .employeeform import EmployeeForm
from .serializers import EmployeeSerializer
from .utils import send_system_email
from .templatetags.translate_tags import translate_text
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.urls import reverse
from django.http import FileResponse, JsonResponse
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Employee, CustomUser, ArchivedUser
from .forms import CustomUserCreationForm
from .serializers import EmployeeSerializer
from .utils import send_system_email
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import (
    QPRRecord, Section1FilesData, Section2MeetingsData, 
    Section3OfficialLanguagesData, Section4HindiLettersData,
    Section5EnglishRepliedHindiData, Section6IssuedLettersData,
    Section7NotingsData, Section8WorkshopsData, 
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData,
    Section11SpecificAchievementsData, UserProfile, ManagerRequest
)
import json

def custom_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')



User = get_user_model()

def home(request): 
    return render(request, 'home.html')

def universal_error_view(request, exception=None, status_code=500):
    lang = request.session.get('lang', 'en')
    error_map = {
        400: {'title': "Bad Request",'msg': "The server could not understand the request due to invalid syntax."},
        403: {'title': "Security Verification Failed",'msg': "You do not have permission to access this resource or your session has expired."},
        404: {'title': "Page Not Found",'msg': "The page you are looking for might have been removed or does not exist."},
        500: {'title': "Internal Server Error",'msg': "Something went wrong on our end. We're working on fixing it."}}
    config = error_map.get(status_code, error_map[500])
    context = {'current_lang': lang,'status_code': status_code,'error_title': config['title'],'error_message': config['msg'],}
    return render(request, 'error.html', context, status=status_code)
def error_400(request, exception=None): return universal_error_view(request, exception, 400)
def error_403(request, exception=None): return universal_error_view(request, exception, 403)
def csrf_failure(request, reason=""): return universal_error_view(request, exception=None, status_code=403)
def error_404(request, exception=None): return universal_error_view(request, exception, 404)
def error_500(request): return universal_error_view(request, None, 500)
@login_required
def dashboard(request):
    role = request.session.get('active_role', request.user.role)

    if 'active_role' not in request.session:
        request.session['active_role'] = role

    # QPR Role Routing
    if role == 'admin':
        return redirect('/qpr/admin/dashboard/')
    
    elif role == 'hod':
        return redirect('/qpr/hod/dashboard/')
    
    elif role == 'user':
        return render(request, "dashboard.html")


    # Main Website Roles
    elif role == 'manager':
        return redirect('manager_dashboard')

    elif role == 'backup_user':
        return render(request, "dashboard.html")

    return redirect('home')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def toggle_language(request):
    current = request.session.get('lang', 'en')
    request.session['lang'] = 'hi' if current == 'en' else 'en'
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def user_detail_view(request, user_id):
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

def is_superuser(user):
    if user.is_superuser:
        return True
    raise PermissionDenied

@user_passes_test(is_superuser)
def privacy_audit_report(request):
    logs = DataAccessLog.objects.all().order_by('-access_time')
    lang = request.session.get('lang', 'en')
    return render(request, 'privacy_audit.html', {'logs': logs, 'current_lang': lang})


@login_required
def delete_account(request):
    if request.method == "POST":
        request.user.delete()
        logout(request)
        messages.success(request, "Your personal data has been erased successfully.")
        return redirect('login')
    return render(request, 'registration/confirm_erasure.html')

class CustomLoginView(LoginView):
    authentication_form = CustomLoginForm
    template_name = 'registration/login.html'

    def get_success_url(self):
        return reverse('dashboard')

    def form_valid(self, form):
        # 1. Log the user in FIRST (this prevents session flushing from wiping your data)
        user = form.get_user()
        auth_login(self.request, user)
        
        # 2. Get data safely from the cleaned form (not raw POST)
        selected_role = form.cleaned_data.get('role')
        current_lang = self.request.session.get('lang', 'en')
        
        # 3. Update the User's Database Record
        user.role = selected_role
        user.save(update_fields=['role'])
        
        # 4. Set Session Data & Force Save
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
            user = form.save()
            # Send welcome email
            send_system_email(user, request, 'welcome')
            
            # Login
            auth_login(request, user)
            
            request.session['lang'] = lang
            request.session['active_role'] = 'user'
            request.session.save()
            
            if not Employee.objects.filter(empcode=user.username).exists():
                Employee.objects.create(
                    empcode=user.username,
                    ename=user.first_name or "", # If you added ename to form
                    status='draft'
                )

            messages.success(request, "Account created successfully!")
            return redirect('dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    
    return render(request, 'registration/signup.html', {'form': form})

def send_otp_email(user, lang):
    user.otp = str(random.randint(100000, 999999))
    user.otp_created_at = timezone.now()
    user.save(update_fields=['otp', 'otp_created_at'])    
    send_system_email(
        user, 
        None, 
        'otp', 
        extra_context={
            'otp': user.otp,
            'lang': lang  # This allows the email template to use {% if lang == 'hi' %}
        }
    )
    return user.otp
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
                messages.success(request, translate_text("OTP sent successfully to your registered email.", lang))
                return redirect('verify_otp')
        
        messages.error(request, translate_text("User with this username does not exist.", lang))
        return redirect('forgot_password')

class VerifyOTPView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash'): return redirect('forgot_password')
        lang = request.session.get('lang', 'en')        
        context = {
            'title_text': translate_text("Verify OTP", lang), 
            'button_text': translate_text("Verify Code", lang),
            'current_lang': lang
        }
        return render(request, 'registration/verify_otp.html', context)

    def post(self, request):
        email_hash = request.session.get('reset_email_hash')
        otp_input = request.POST.get('otp')
        lang = request.session.get('lang', 'en')
        att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
        
        if cache.get(blk_key): 
            return render(request, 'registration/verify_otp.html', {
                'is_blocked': True, 
                'current_lang': lang
            })

        user = CustomUser.objects.filter(email_hash=email_hash).first()
        
        if user and user.otp == otp_input:
            if (timezone.now() - user.otp_created_at).total_seconds() < 300:
                request.session['otp_verified'] = True 
                return redirect('reset_password')
        
        attempts = cache.get(att_key, 0) + 1
        cache.set(att_key, attempts, 600)
        if attempts >= 5: 
            cache.set(blk_key, True, 600)
        
        messages.error(request, translate_text("Invalid or expired OTP.", lang))
        return render(request, 'registration/verify_otp.html', {'current_lang': lang})
    pass

class ResendOTPView(View):
    def get(self, request):
        email_hash = request.session.get('reset_email_hash')
        if not email_hash:
            return redirect('forgot_password')
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        if not user:
            return redirect('forgot_password')

        lang = request.session.get('lang', 'en')
        send_otp_email(user, lang)
        messages.success(request, translate_text("A new OTP has been sent to your email.", lang))
        return redirect('verify_otp')
        

class ResetPasswordView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash'): return redirect('forgot_password')
        return render(request, 'registration/reset_password.html')

    def post(self, request):
        email_hash = request.session.get('reset_email_hash')
        pwd = request.POST.get('password')
        cfm = request.POST.get('confirm_password')
        lang = request.session.get('lang', 'en')
        
        if not email_hash: return redirect('forgot_password')

        if pwd == cfm:
            user = CustomUser.objects.filter(email_hash=email_hash).first()
            if user:
                user.set_password(pwd)
                user.otp = None 
                user.save()
                send_system_email(user, request, 'reset')
                request.session.pop('reset_email_hash', None)
                messages.success(request, translate_text("Password reset successfully. Please login.", lang))
            return redirect('login')
        messages.error(request, translate_text("Passwords do not match.", lang))
        return render(request, 'registration/reset_password.html')
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
        p.drawString(50, y, f"{log.access_time.strftime('%Y-%m-%d')}: {log.accessed_by.username} -> {log.target_user.username}")
        y -= 20
        if y < 50: p.showPage(); y = height - 50

    p.showPage()
    p.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='privacy_audit.pdf')

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
def freeze_profile(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    user.is_frozen = True
    user.save()
    send_system_email(user, request, 'freeze')
    messages.success(request, translate_text("Your profile has been frozen. You can no longer edit it without manager approval.", lang))
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

@user_passes_test(lambda u: u.is_authenticated and (u.role in ['manager', 'admin'] or u.is_superuser))
def manager_dashboard(request):
    # 1. USERS TAB DATA: All registered accounts
    # We fetch all users to manage their login access (Archive/Restore)
    users = CustomUser.objects.all().order_by('-date_joined')
    
    # 2. RECORDS TAB DATA: All employee forms submitted
    # We fetch actual data records to manage Designations and Edit Permissions
    employees = Employee.objects.all().order_by('-lastupdate')

    return render(request, 'manager_dashboard.html', {
        'users': users, 
        'employees': employees
    })

@user_passes_test(lambda u: u.role in ['manager', 'admin'])
def update_designation(request, user_id):
    if request.method == "POST":
        target_user = get_object_or_404(CustomUser, id=user_id)
        new_designation = request.POST.get('designation')
        
        # Find the employee record
        employee = Employee.objects.filter(empcode=target_user.username).first()
        
        if employee:
            employee.designation = new_designation
            employee.save()
            messages.success(request, f"Designation for {target_user.username} updated to {new_designation}.")
        else:
            messages.error(request, "Employee record not found for this user.")
            
    return redirect('manager_dashboard')

@user_passes_test(lambda u: u.is_authenticated and (u.role in ['manager', 'admin'] or u.is_superuser))
def manage_user_action(request, user_id, action):
    target_user = get_object_or_404(CustomUser, id=user_id)
    lang = request.session.get('lang', 'en')
    
    # --- ADMIN ONLY ACTIONS ---
    if action in ['archive', 'unarchive']:
        if request.user.role != 'admin' and not request.user.is_superuser:
            messages.error(request, translate_text("Only Admins can perform this action.", lang))
            return redirect('manager_dashboard')
            
        if action == 'archive':
            # Your existing archive logic
            target_user.is_active = False
            target_user.is_archived = True
            target_user.save()
            messages.success(request, translate_text("User archived successfully.", lang))
            
        elif action == 'unarchive':
            target_user.is_active = True
            target_user.is_archived = False
            target_user.save()
            messages.success(request, translate_text("User restored successfully.", lang))

    # --- MANAGER & ADMIN ACTIONS (RECORDS) ---
    elif action == 'unlock_record':
        # This unlocks the Employee Form so the user can edit it again
        employee = Employee.objects.filter(empcode=target_user.username).first()
        if employee:
            employee.status = 'draft' # Revert to draft
            employee.save()
            
            target_user.is_edit_allowed = True # Unlock profile if frozen
            target_user.save()
            
            messages.success(request, translate_text("Record unlocked. User can now edit their data.", lang))
        else:
            messages.error(request, translate_text("No employee record found for this user.", lang))

    return redirect('manager_dashboard')

def archive_user_action(user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    
    # Still create the snapshot for history
    employee = Employee.objects.filter(empcode=user.username).first()
    snapshot = {}
    if employee:
        snapshot = {
            "name": employee.ename,
            "designation": employee.designation,
            "status": employee.status,
            "last_updated": str(employee.lastupdate)
        }

    ArchivedUser.objects.create(
        username=user.username,
        email_hash=user.email_hash,
        encrypted_email_data=user.encrypted_email_data,
        original_user_id=user.id,
        employee_snapshot=json.dumps(snapshot) 
    )
    
    
    user.is_active = False    # Stops login
    user.is_archived = True   # Marks as archived
    user.save()


@user_passes_test(lambda u: u.is_superuser)
def download_privacy_audit(request):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Add Header
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "DPDP Privacy Audit Report")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 65, f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    
    y = height - 100
    logs = DataAccessLog.objects.all().order_by('-access_time')
    for log in logs:
        line = f"{log.access_time.strftime('%Y-%m-%d %H:%M')}: {log.accessed_by.username} accessed {log.target_user.username} ({log.reason})"
        p.drawString(50, y, line)
        y -= 20
        if y < 50: 
            p.showPage()
            y = height - 50

    p.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'privacy_audit_{timezone.now().date()}.pdf')



def unarchive_user_action(archived_id):
    archived = get_object_or_404(ArchivedUser, id=archived_id)
    user = CustomUser.objects.create(
        username=archived.username,
        email_hash=archived.email_hash,
        encrypted_email_data=archived.encrypted_email_data,
        is_archived=False,
        role='user' 
    )    
    archived.delete()


def custom_captcha_audio(request, key):
    # 1. Retrieve the text for this captcha hashkey
    try:
        captcha = CaptchaStore.objects.get(hashkey=key)
    except CaptchaStore.DoesNotExist:
        raise Http404("Captcha not found")

    spaced_text = " ".join(list(captcha.response))
    
    tts = gTTS(text=spaced_text, lang='en')
    
    mp3_fp = io.BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)
    
    return HttpResponse(mp3_fp.read(), content_type="audio/mpeg")


@login_required
def employee_form(request):
    if request.session.get('active_role') != 'user':
        return redirect('dashboard')
    
    form = EmployeeForm()
    return render(request, "employeeform.html", {"form": form})

class EmployeeListCreateAPI(APIView):
    def get(self, request):
        if request.session.get('active_role') != 'user':
            return Response({"error": "Unauthorized"}, status=403)
            
        status_filter = request.GET.get("status")
        qs = Employee.objects.all().order_by("-lastupdate")
        if status_filter:
            qs = qs.filter(status=status_filter)
            
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
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return None

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
        count = Employee.objects.filter(id__in=ids, status="draft").update(
            status="submitted", lastupdate=timezone.now()
        )
        return Response({"message": f"{count} record(s) submitted"})
@user_passes_test(lambda u: u.role == 'backup_user', login_url='login')
def download_db_backup(request):
    """Securely serve the SQLite database file."""
    db_path = settings.DATABASES['default']['NAME']
    if os.path.exists(db_path):
        return FileResponse(open(db_path, 'rb'), as_attachment=True, filename='backup_RajyaBhasha.sqlite3')
    
    messages.error(request, "Database file not found.")
    return redirect('dashboard')

User = get_user_model()
# Helper function to get active HODs for dropdown
def get_active_hods():
    """Get list of all active HODs for registration dropdown"""
    # Get HODs with role='hod'
    hod_names = list(UserProfile.objects.filter(role='hod').values_list('hod_name', flat=True).distinct())
    
    # Also add users with hod_name=None as their own HODs (using their first_name)
    unassigned_hod_names = list(UserProfile.objects.filter(
        role='user', 
        hod_name__isnull=True
    ).values_list('user__first_name', flat=True).distinct())
    
    # Combine and sort
    all_hod_names = sorted(set(hod_names + unassigned_hod_names))
    return all_hod_names


def serialize_qpr_record(record):
    """
    Serialize a QPRRecord with all related sections into a dictionary.
    This replaces the old JSON field approach with proper ORM data.
    """
    data = {
        'id': record.id,
        'officeName': record.officeName,
        'officeCode': record.officeCode,
        'region': record.region,
        'quarter': record.quarter,
        'year': record.year or '2025-2026',
        'status': record.status,
        'phone': record.phone or '',
        'email': record.email or '',
        'details': {}
    }
    
    # Section 1 Data
    if hasattr(record, 'section1'):
        s1 = record.section1
        data['details'].update({
            's1_total': s1.total_files or '',
            's1_hindi': s1.hindi_files or '',
        })
    
    # Section 2 Data
    if hasattr(record, 'section2'):
        s2 = record.section2
        data['details'].update({
            's2_meetings': s2.meetings_count or '',
            's2_minutes': s2.hindi_minutes or '',
            's2_papers_total': s2.total_papers or '',
            's2_papers_hindi': s2.hindi_papers or '',
        })
    
    # Section 3 Data
    if hasattr(record, 'section3'):
        s3 = record.section3
        data['details'].update({
            's3_total': s3.total_documents or '',
            's3_bilingual': s3.bilingual_documents or '',
            's3_english': s3.english_only_documents or '',
            's3_hindi_only': s3.hindi_only_documents or '',
        })
    
    # Section 4 Data
    if hasattr(record, 'section4'):
        s4 = record.section4
        data['details'].update({
            's4_total': s4.total_letters or '',
            's4_no_reply': s4.no_reply_letters or '',
            's4_replied_hindi': s4.replied_hindi_letters or '',
            's4_replied_eng': s4.replied_english_letters or '',
        })
    
    # Section 5 Data
    if hasattr(record, 'section5'):
        s5 = record.section5
        data['details'].update({
            's5_total': s5.region_a_english_letters or '',
            's5_hindi': s5.region_a_replied_hindi or '',
            's5_english': s5.region_a_replied_english or '',
            's5_noreply': s5.region_a_no_reply or '',
        })
    
    # Section 6 Data
    if hasattr(record, 'section6'):
        s6 = record.section6
        data['details'].update({
            's6_a_hindi': s6.region_a_hindi_bilingual or '',
            's6_a_eng': s6.region_a_english_only or '',
            's6_a_total': s6.region_a_total or '',
            's6_b_hindi': s6.region_b_hindi_bilingual or '',
            's6_b_eng': s6.region_b_english_only or '',
            's6_b_total': s6.region_b_total or '',
            's6_c_hindi': s6.region_c_hindi_bilingual or '',
            's6_c_eng': s6.region_c_english_only or '',
            's6_c_total': s6.region_c_total or '',
        })
    
    # Section 7 Data (Notings)
    if hasattr(record, 'section7'):
        s7 = record.section7
        data['details'].update({
            's7_hindi': s7.hindi_pages or '',
            's7_eng': s7.english_pages or '',
            's7_total': s7.total_pages or '',
            's7_eoffice': s7.eoffice_notings or '',
        })
    
    # Section 8 Data (Workshops)
    if hasattr(record, 'section8'):
        s8 = record.section8
        data['details'].update({
            's8_workshops': s8.full_day_workshops or '',
            's8_officers': s8.officers_trained or '',
            's8_employees': s8.employees_trained or '',
        })
    
    # Section 9 Data (Implementation Committee)
    if hasattr(record, 'section9'):
        s9 = record.section9
        data['details'].update({
            's9_date': s9.meeting_date.isoformat() if s9.meeting_date else '',
            's9_sub_committees': s9.sub_committees_count or '',
            's9_meetings_count': s9.meetings_organized or '',
            's9_agenda_hindi': s9.agenda_hindi or '',
        })
    
    # Section 10 Data (Hindi Advisory)
    if hasattr(record, 'section10'):
        s10 = record.section10
        data['details'].update({
            's10_date': s10.meeting_date.isoformat() if s10.meeting_date else '',
        })
    
    # Section 11 Data (Achievements)
    if hasattr(record, 'section11'):
        s11 = record.section11
        data['details'].update({
            's12_1': s11.innovative_work or '',
            's12_2': s11.special_events or '',
            's12_3': s11.hindi_medium_works or '',
        })
    
    return data

@login_required
@csrf_exempt
def api_records(request):
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method == 'GET':
        # Return only records for the logged-in user
        records = QPRRecord.objects.filter(user=request.user).order_by('-id')
        records_data = []
        for record in records:
            data = serialize_qpr_record(record)
            
            # Add edit permission info
            edit_approved = False
            if record.is_submitted:
                edit_approved = ManagerRequest.objects.filter(
                    hod=request.user,
                    request_type='qpr',
                    status='approved'
                ).exists()
            
            data['can_edit'] = not record.is_submitted or edit_approved
            data['edit_approved'] = edit_approved
            records_data.append(data)
        
        return JsonResponse(records_data, safe=False)

    elif request.method == 'POST':
        try:
            # 1. Parse the JSON data from the request body
            data = json.loads(request.body)
            
            # 2. Extract ID to see if we are Updating or Creating
            record_id = data.get('id')
            details = data.get('details', {})
            
            if record_id:
                # UPDATE existing record - check if user owns it
                record = QPRRecord.objects.get(pk=record_id, user=request.user)
                record.officeName = data.get('officeName', '')
                record.officeCode = data.get('officeCode', '')
                record.region = data.get('region', '')
                record.quarter = data.get('quarter', '')
                record.status = data.get('status', 'Draft')
                record.phone = data.get('phone', '')
                record.email = data.get('email', '')
                # Set is_submitted based on status
                record.is_submitted = (record.status == 'Submitted')
                record.save()
                
                # If user is saving edits to a submitted record, delete the approved edit request
                # This forces them to request edit approval again
                if record.is_submitted:
                    ManagerRequest.objects.filter(
                        hod=request.user,
                        request_type='qpr',
                        status='approved'
                    ).delete()
                
                # Update or create related section data
                _save_section_data(record, details)
            else:
                # CREATE new record
                is_submitted = (data.get('status', 'Draft') == 'Submitted')
                record = QPRRecord.objects.create(
                    user=request.user,
                    officeName=data.get('officeName', ''),
                    officeCode=data.get('officeCode', ''),
                    region=data.get('region', ''),
                    quarter=data.get('quarter', ''),
                    status=data.get('status', 'Draft'),
                    phone=data.get('phone', ''),
                    email=data.get('email', ''),
                    is_submitted=is_submitted
                )
                
                # Create related section data
                _save_section_data(record, details)

            return JsonResponse({'id': record.id, 'message': 'Saved successfully!'})

        except QPRRecord.DoesNotExist:
            return JsonResponse({'error': 'Record not found or access denied'}, status=404)
        except Exception as e:
            # This prints the actual error to your terminal so you can see it
            print("SERVER ERROR:", e)
            return JsonResponse({'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        record_id = request.GET.get('id')
        if record_id:
            QPRRecord.objects.filter(pk=record_id, user=request.user).delete()
            return JsonResponse({'message': 'Deleted'})
            
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
@csrf_exempt
def request_edit_api(request):
    """Handle requests to edit submitted QPR/Profile records"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request_type = data.get('request_type')  # 'qpr' or 'profile'
            record_id = data.get('record_id')  # For QPR records
            reason = data.get('reason', '')
            
            if request_type == 'qpr':
                # Get the QPR record
                record = QPRRecord.objects.get(pk=record_id, user=request.user)
                
                # Get admin user(s) - only Admin approves/rejects edit requests
                admin_users = User.objects.filter(profile__role='admin')
                
                if not admin_users.exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'No Admin users found in the system'
                    }, status=400)
                
                # Create a request for each admin recipient (only Admin approves)
                for admin_user in admin_users:
                    ManagerRequest.objects.create(
                        hod=request.user,  # The person making the request
                        user=admin_user,   # The Admin receiving it
                        request_type='qpr',
                        reason=f"Edit request for QPR ({record.officeName} - {record.quarter}): {reason}"
                    )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Request sent to Admin for approval'
                })
            
            elif request_type == 'profile':
                # Get admin user(s) - only Admin approves/rejects edit requests
                admin_users = User.objects.filter(profile__role='admin')
                
                if not admin_users.exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'No Admin users found in the system'
                    }, status=400)
                
                # Create a request for each admin recipient
                for admin_user in admin_users:
                    ManagerRequest.objects.create(
                        hod=request.user,  # The person making the request
                        user=admin_user,   # The Admin receiving it
                        request_type='profile',
                        reason=f"Edit request for profile: {reason}"
                    )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Request sent to Admin for approval'
                })
            
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid request type'
                }, status=400)
            
        except QPRRecord.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Record not found'
            }, status=404)
        except Exception as e:
            print("SERVER ERROR:", e)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=400)


def _save_section_data(record, details):
    """
    Helper function to save all section data from the details dictionary.
    Uses get_or_create for each section to handle both new and existing records.
    """
    # Section 1
    section1, _ = Section1FilesData.objects.get_or_create(qpr_record=record)
    section1.total_files = _convert_to_int(details.get('s1_total'))
    section1.hindi_files = _convert_to_int(details.get('s1_hindi'))
    section1.save()
    
    # Section 2
    section2, _ = Section2MeetingsData.objects.get_or_create(qpr_record=record)
    section2.meetings_count = _convert_to_int(details.get('s2_meetings'))
    section2.hindi_minutes = _convert_to_int(details.get('s2_minutes'))
    section2.total_papers = _convert_to_int(details.get('s2_papers_total'))
    section2.hindi_papers = _convert_to_int(details.get('s2_papers_hindi'))
    section2.save()
    
    # Section 3
    section3, _ = Section3OfficialLanguagesData.objects.get_or_create(qpr_record=record)
    section3.total_documents = _convert_to_int(details.get('s3_total'))
    section3.bilingual_documents = _convert_to_int(details.get('s3_bilingual'))
    section3.english_only_documents = _convert_to_int(details.get('s3_english'))
    section3.hindi_only_documents = _convert_to_int(details.get('s3_hindi_only'))
    section3.save()
    
    # Section 4
    section4, _ = Section4HindiLettersData.objects.get_or_create(qpr_record=record)
    section4.total_letters = _convert_to_int(details.get('s4_total'))
    section4.no_reply_letters = _convert_to_int(details.get('s4_no_reply'))
    section4.replied_hindi_letters = _convert_to_int(details.get('s4_replied_hindi'))
    section4.replied_english_letters = _convert_to_int(details.get('s4_replied_eng'))
    section4.save()
    
    # Section 5
    section5, _ = Section5EnglishRepliedHindiData.objects.get_or_create(qpr_record=record)
    section5.region_a_english_letters = _convert_to_int(details.get('s5_total'))
    section5.region_a_replied_hindi = _convert_to_int(details.get('s5_hindi'))
    section5.region_a_replied_english = _convert_to_int(details.get('s5_english'))
    section5.region_a_no_reply = _convert_to_int(details.get('s5_noreply'))
    section5.save()
    
    # Section 6
    section6, _ = Section6IssuedLettersData.objects.get_or_create(qpr_record=record)
    section6.region_a_hindi_bilingual = _convert_to_int(details.get('s6_a_hindi'))
    section6.region_a_english_only = _convert_to_int(details.get('s6_a_eng'))
    section6.region_a_total = _convert_to_int(details.get('s6_a_total'))
    section6.region_b_hindi_bilingual = _convert_to_int(details.get('s6_b_hindi'))
    section6.region_b_english_only = _convert_to_int(details.get('s6_b_eng'))
    section6.region_b_total = _convert_to_int(details.get('s6_b_total'))
    section6.region_c_hindi_bilingual = _convert_to_int(details.get('s6_c_hindi'))
    section6.region_c_english_only = _convert_to_int(details.get('s6_c_eng'))
    section6.region_c_total = _convert_to_int(details.get('s6_c_total'))
    section6.save()
    
    # Section 7 (Notings)
    section7, _ = Section7NotingsData.objects.get_or_create(qpr_record=record)
    section7.hindi_pages = _convert_to_int(details.get('s7_hindi'))
    section7.english_pages = _convert_to_int(details.get('s7_eng'))
    section7.total_pages = _convert_to_int(details.get('s7_total'))
    section7.eoffice_notings = _convert_to_int(details.get('s7_eoffice'))
    section7.save()
    
    # Section 8 (Workshops)
    section8, _ = Section8WorkshopsData.objects.get_or_create(qpr_record=record)
    section8.full_day_workshops = _convert_to_int(details.get('s8_workshops'))
    section8.officers_trained = _convert_to_int(details.get('s8_officers'))
    section8.employees_trained = _convert_to_int(details.get('s8_employees'))
    section8.save()
    
    # Section 9 (Implementation Committee)
    section9, _ = Section9ImplementationCommitteeData.objects.get_or_create(qpr_record=record)
    section9.meeting_date = _convert_to_date(details.get('s9_date'))
    section9.sub_committees_count = _convert_to_int(details.get('s9_sub_committees'))
    section9.meetings_organized = _convert_to_int(details.get('s9_meetings_count'))
    section9.agenda_hindi = details.get('s9_agenda_hindi', '')
    section9.save()
    
    # Section 10 (Hindi Advisory)
    section10, _ = Section10HindiAdvisoryData.objects.get_or_create(qpr_record=record)
    section10.meeting_date = _convert_to_date(details.get('s10_date'))
    section10.save()
    
    # Section 11 (Achievements)
    section11, _ = Section11SpecificAchievementsData.objects.get_or_create(qpr_record=record)
    section11.innovative_work = details.get('s12_1', '')
    section11.special_events = details.get('s12_2', '')
    section11.hindi_medium_works = details.get('s12_3', '')
    section11.save()


def _convert_to_int(value):
    """Convert value to integer, handling empty strings and None"""
    if value == '' or value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _convert_to_date(value):
    """Convert value to date, handling empty strings and None"""
    if value == '' or value is None:
        return None
    try:
        from datetime import datetime
        # Handle ISO format dates
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value
    except (ValueError, TypeError, AttributeError):
        return None

@login_required
def api_record_detail(request, record_id):
    """
    Return a single record as JSON by id with all related section data.
    Only if user owns it.
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        
        record = QPRRecord.objects.get(pk=record_id, user=request.user)
        data = serialize_qpr_record(record)
        
        # Check if user has an approved edit request for this record
        edit_approved = False
        if record.is_submitted:
            # Look for an approved edit request FROM this user (sent TO admin)
            edit_approved = ManagerRequest.objects.filter(
                hod=request.user,
                request_type='qpr',
                status='approved'
            ).exists()
        
        # Add edit permission info to response
        data['can_edit'] = not record.is_submitted or edit_approved
        data['edit_approved'] = edit_approved
        
        return JsonResponse(data, safe=False)
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Record not found or access denied'}, status=404)




# ==================== USER VIEWS ====================

# @login_required
def user_profile(request):
    profile = request.user.profile

    profile_submitted = profile.profile_updated
    profile_edit_approved = False
    profile_edit_pending = False

    if profile_submitted:
        approved_request = ManagerRequest.objects.filter(
            hod=request.user,
            request_type='profile',
            status='approved'
        ).first()

        profile_edit_approved = approved_request is not None

        pending_request = ManagerRequest.objects.filter(
            hod=request.user,
            request_type='profile',
            status='pending'
        ).first()

        profile_edit_pending = pending_request is not None

    if request.method == 'POST':
        email = request.POST.get('email')

        if not email:
            messages.error(request, 'Email is required')
        elif profile_submitted and not profile_edit_approved:
            messages.error(
                request,
                'You cannot edit a submitted profile. Please request approval from Admin first.'
            )
        else:
            profile.email = email
            profile.profile_updated = True
            profile.save()

            request.user.email = email
            request.user.save()

            if profile_edit_approved:
                ManagerRequest.objects.filter(
                    hod=request.user,
                    request_type='profile',
                    status='approved'
                ).delete()

                messages.success(
                    request,
                    'Profile updated successfully! Please request approval if you need further changes.'
                )
            else:
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
def qpr_form(request):
    return render(request, 'qpr/qpr_form.html')


@login_required
def user_dashboard(request):
    """User dashboard with QPR and profile status"""
    profile, created = UserProfile.objects.get_or_create(
    user=request.user,
    defaults={
        "employee_code": f"EMP{request.user.id}",
        "role": request.user.role
    }
)
    
    # If profile is not updated, redirect to profile update page
    if not profile.profile_updated:
        messages.warning(request, 'Please complete your profile first!')
        return redirect('qpr_user_profile')
    
    qpr_records = QPRRecord.objects.filter(user=request.user)
    
    # Check if profile is updated
    profile_status = 'Updated' if profile.profile_updated else 'Needs Update'
    
    # Count submitted QPRs
    submitted_qprs = qpr_records.filter(is_submitted=True).count()
    total_qprs = qpr_records.count()
    
    context = {
        'profile': profile,
        'profile_status': profile_status,
        'qpr_submitted': submitted_qprs > 0,
        'qpr_count': total_qprs,
    }
    return render(request, 'qpr/user_dashboard.html', context)


# ==================== HOD VIEWS ====================

@login_required
def hod_dashboard(request):
    """HOD dashboard showing people under them and QPR status"""
    if request.user.profile.role != 'hod':
        messages.error(request, 'Access denied. HOD only.')
        return redirect('/')
    
    hod_name = request.user.profile.hod_name
    
    # Get all users under this HOD
    users_under_hod = UserProfile.objects.filter(
        role='user',
        hod_name=hod_name
    )
    
    total_users = users_under_hod.count()
    
    # Count QPR submitted
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
    return render(request, 'qpr/hod_dashboard.html', context)


@login_required
def hod_detail_list(request):
    """List all users under HOD with their completion status"""
    if request.user.profile.role != 'hod':
        messages.error(request, 'Access denied. HOD only.')
        return redirect('/')
    
    hod_name = request.user.profile.hod_name
    
    # Get all users under this HOD
    users_under_hod = UserProfile.objects.filter(
        role='user',
        hod_name=hod_name
    ).select_related('user')
    
    users_data = []
    for user_profile in users_under_hod:
        user = user_profile.user
        qpr_records = user.qpr_records.all()
        
        # Get office code and name from first submitted QPR
        office_code = ''
        office_name = ''
        
        if qpr_records.exists():
            first_qpr = qpr_records.first()
            office_code = first_qpr.officeCode
            office_name = first_qpr.officeName
        
        # Check completion status
        profile_complete = user_profile.profile_updated
        qpr_complete = qpr_records.filter(is_submitted=True).exists()
        
        # Check if this user has a pending edit request (sent to Admin)
        has_pending_edit_request = ManagerRequest.objects.filter(
            hod=user,
            request_type='qpr',
            status='pending'
        ).exists()
        
        users_data.append({
            'profile': user_profile,
            'user': user,
            'employee_code': user_profile.employee_code,
            'name': user_profile.name or 'Not Set',
            'office_code': office_code,
            'office_name': office_name,
            'profile_complete': profile_complete,
            'qpr_complete': qpr_complete,
            'email': user.email,
            'has_pending_edit_request': has_pending_edit_request,
        })
    
    context = {
        'users_data': users_data,
        'hod_name': hod_name
    }
    return render(request, 'qpr/hod_detail_list.html', context)


@login_required
def hod_manager_requests(request):
    """HOD can send requests to manager for profile/QPR changes"""
    if request.user.profile.role != 'hod':
        messages.error(request, 'Access denied. HOD only.')
        return redirect('/')
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        request_type = request.POST.get('request_type')
        reason = request.POST.get('reason', '')
        
        try:
            user = User.objects.get(id=user_id)
            # Check if user is under this HOD
            if user.profile.hod_name != request.user.profile.hod_name:
                messages.error(request, 'User is not under your HOD group')
                return redirect('hod_manager_requests')
            
            ManagerRequest.objects.create(
                hod=request.user,
                user=user,
                request_type=request_type,
                reason=reason
            )
            messages.success(request, 'Request sent to manager successfully!')
        except User.DoesNotExist:
            messages.error(request, 'User not found')
    
    hod_name = request.user.profile.hod_name
    
    # Get all users under this HOD
    users_under_hod = UserProfile.objects.filter(
        role='user',
        hod_name=hod_name
    ).select_related('user')
    
    users_data = []
    for user_profile in users_under_hod:
        user = user_profile.user
        qpr_records = user.qpr_records.all()
        
        # Get office code and name
        office_code = ''
        office_name = ''
        if qpr_records.exists():
            first_qpr = qpr_records.first()
            office_code = first_qpr.officeCode
            office_name = first_qpr.officeName
        
        # Check completion status
        profile_complete = user_profile.profile_updated
        qpr_complete = qpr_records.filter(is_submitted=True).exists()
        
        users_data.append({
            'user': user,
            'employee_code': user_profile.employee_code,
            'name': user_profile.name or 'Not Set',
            'office_code': office_code,
            'office_name': office_name,
            'profile_complete': profile_complete,
            'qpr_complete': qpr_complete,
        })
    
    context = {
        'users_data': users_data,
        'hod_name': hod_name
    }
    return render(request, 'qpr/hod_manager_requests.html', context)


# ==================== ADMIN/MANAGER VIEWS ====================

@login_required
def admin_dashboard(request):
    if request.user.profile.role != 'admin':
        return redirect('/')

    hod_data = []
    
    # Get all HODs with role='hod' and display them with their stats
    hods = UserProfile.objects.filter(role='hod').order_by('name')
    
    for hod_profile in hods:
        # Use hod_name as the key to match users
        hod_key = hod_profile.hod_name or hod_profile.name or hod_profile.employee_code
        
        # Display name for the table
        hod_display = hod_profile.name or hod_key or 'UNKNOWN'
        
        # Find users assigned to this HOD (case-insensitive)
        users_under_hod = UserProfile.objects.filter(
            role='user',
            hod_name__iexact=hod_key
        )
        
        total_users = users_under_hod.count()
        profile_complete = sum(1 for p in users_under_hod if p.profile_updated)
        qpr_complete = sum(
            1 for p in users_under_hod
            if QPRRecord.objects.filter(user=p.user, status='Submitted').exists()
        )
        
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        
        hod_data.append({
            'hod_name': str(hod_display).upper(),
            'total_users': total_users,
            'profile_complete': profile_complete,
            'qpr_complete': qpr_complete,
            'completion_pct': completion_pct,
            'employee_code': hod_profile.employee_code,
        })
    
    # Also add HOD groups for all unique hod_name values in users (even if no actual HOD exists)
    all_users = UserProfile.objects.filter(role='user')
    
    # Get unique hod_name values from users (excluding None)
    unique_hod_names = set()
    for user in all_users:
        if user.hod_name:  # Non-null hod_name
            unique_hod_names.add(user.hod_name)
    
    # Remove hod_name values that are already covered by actual HODs
    actual_hod_names = set(UserProfile.objects.filter(role='hod').values_list('hod_name', flat=True))
    uncovered_hod_names = unique_hod_names - actual_hod_names
    
    # Add stats for uncovered HOD names
    for hod_name in sorted(uncovered_hod_names):
        users_under_hod = UserProfile.objects.filter(
            role='user',
            hod_name__iexact=hod_name
        )
        
        total_users = users_under_hod.count()
        profile_complete = sum(1 for p in users_under_hod if p.profile_updated)
        qpr_complete = sum(
            1 for p in users_under_hod
            if QPRRecord.objects.filter(user=p.user, status='Submitted').exists()
        )
        
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        
        hod_data.append({
            'hod_name': str(hod_name).upper(),
            'total_users': total_users,
            'profile_complete': profile_complete,
            'qpr_complete': qpr_complete,
            'completion_pct': completion_pct,
            'employee_code': '',  # No employee code for uncovered HOD names
        })
    
    # Add each user who is their own HOD (hod_name=None)
    own_hods = UserProfile.objects.filter(role='user', hod_name__isnull=True).order_by('user__first_name')
    
    for user in own_hods:
        # Each such user is treated as their own HOD with 0 employees
        display_name = user.user.first_name or user.name or user.employee_code or 'UNKNOWN'
        hod_data.append({
            'hod_name': str(display_name).upper(),
            'total_users': 0,
            'profile_complete': 0,
            'qpr_complete': 0,
            'completion_pct': 0,
        })

    # Get only pending requests FROM USERS (not from HODs)
    # Filter where the 'hod' field (requester) has role='user'
    pending_requests = ManagerRequest.objects.filter(
        status='pending',
        hod__profile__role='user'  # Request is FROM a user
    ).select_related('hod', 'user')

    manager_requests = [
        {
            'id': r.id,
            'hod_name': r.hod.profile.employee_code,
            'user_name': r.user.profile.name or r.user.profile.employee_code,
            'request_type': r.request_type,
            'reason': r.reason,
            'created_at': r.created_at,
        }
        for r in pending_requests
    ]

    context = {
        'hod_data': hod_data,
        'manager_requests': manager_requests,
        'total_hods': len(hod_data),
    }

    return render(request, 'qpr/admin_dashboard.html', context)



@login_required
def admin_approve_request(request, request_id):
    """Admin approves a manager request"""
    if request.user.profile.role != 'admin':
        messages.error(request, 'Access denied. Admin only.')
        return redirect('/')
    
    try:
        manager_request = ManagerRequest.objects.get(id=request_id)
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'approve':
                manager_request.status = 'approved'
                manager_request.save()
                messages.success(request, 'Request approved successfully!')
            elif action == 'reject':
                manager_request.status = 'rejected'
                manager_request.save()
                messages.success(request, 'Request rejected!')
        
        return redirect('admin_dashboard')
    except ManagerRequest.DoesNotExist:
        messages.error(request, 'Request not found')
        return redirect('qpr_admin_dashboard')# New view functions to add to views.py

@login_required
def admin_employee_list(request):
    """Admin view to see all employees organized by HOD"""
    if request.user.profile.role != 'admin':
        messages.error(request, 'Access denied. Admin only.')
        return redirect('/')
    
    # Get filter parameters
    employee_code_filter = request.GET.get('employee_code', '').strip()
    name_filter = request.GET.get('name', '').strip()
    quarter_filter = request.GET.get('quarter', '').strip()
    year_filter = request.GET.get('year', '').strip()
    
    # Get all HODs with role='hod' and their users
    hods = UserProfile.objects.filter(role='hod').order_by('name')
    
    hod_groups = []
    for hod_profile in hods:
        users_under_hod = UserProfile.objects.filter(
            role='user',
            hod_name=hod_profile.hod_name
        ).order_by('name')
        
        # Build user data with QPR status
        user_details = []
        for user_profile in users_under_hod:
            # Apply employee code filter
            if employee_code_filter and employee_code_filter.lower() not in user_profile.employee_code.lower():
                continue
            
            # Apply name filter
            if name_filter:
                user_name = user_profile.name or user_profile.user.get_full_name() or user_profile.user.username
                if name_filter.lower() not in user_name.lower():
                    continue
            
            qpr_records = QPRRecord.objects.filter(user=user_profile.user).order_by('-id')
            latest_qpr = qpr_records.first() if qpr_records else None
            
            # Apply quarter filter
            if quarter_filter:
                if not latest_qpr or quarter_filter.lower() not in (latest_qpr.quarter or '').lower():
                    continue
            
            # Apply year filter
            if year_filter:
                if not latest_qpr or year_filter != (latest_qpr.year or ''):
                    continue
            
            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_profile.name or user_profile.user.get_full_name() or user_profile.user.username,
                'email': user_profile.user.email,
                'office_name': user_profile.office_name or (latest_qpr.officeName if latest_qpr else 'Not Set'),
                'office_code': user_profile.office_code or (latest_qpr.officeCode if latest_qpr else 'Not Set'),
                'quarter': latest_qpr.quarter if latest_qpr else 'Not Set',
                'year': latest_qpr.year if latest_qpr else 'Not Set',
                'qpr_status': latest_qpr.status if latest_qpr else 'Not Submitted',
            })
        
        if user_details:  # Only show HOD group if has users after filtering
            hod_groups.append({
                'hod_name': hod_profile.hod_name,
                'hod_email': hod_profile.user.email,
                'hod_emp_code': hod_profile.employee_code,
                'user_count': len(user_details),
                'users': user_details
            })
    
    # Also add HOD groups for all unique hod_name values in users (even if no actual HOD exists)
    all_users = UserProfile.objects.filter(role='user')
    
    # Get unique hod_name values from users (excluding None)
    unique_hod_names = set()
    for user in all_users:
        if user.hod_name:  # Non-null hod_name
            unique_hod_names.add(user.hod_name)
    
    # Remove hod_name values that are already covered by actual HODs
    actual_hod_names = set(UserProfile.objects.filter(role='hod').values_list('hod_name', flat=True))
    uncovered_hod_names = unique_hod_names - actual_hod_names
    
    # Add groups for uncovered HOD names
    for hod_name in sorted(uncovered_hod_names):
        users_under_hod = UserProfile.objects.filter(
            role='user',
            hod_name__iexact=hod_name
        ).order_by('name')
        
        # Build user data with QPR status
        user_details = []
        for user_profile in users_under_hod:
            # Apply employee code filter
            if employee_code_filter and employee_code_filter.lower() not in user_profile.employee_code.lower():
                continue
            
            # Apply name filter
            if name_filter:
                user_name = user_profile.name or user_profile.user.get_full_name() or user_profile.user.username
                if name_filter.lower() not in user_name.lower():
                    continue
            
            qpr_records = QPRRecord.objects.filter(user=user_profile.user).order_by('-id')
            latest_qpr = qpr_records.first() if qpr_records else None
            
            # Apply quarter filter
            if quarter_filter:
                if not latest_qpr or quarter_filter.lower() not in (latest_qpr.quarter or '').lower():
                    continue
            
            # Apply year filter
            if year_filter:
                if not latest_qpr or year_filter != (latest_qpr.year or ''):
                    continue
            
            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_profile.name or user_profile.user.get_full_name() or user_profile.user.username,
                'email': user_profile.user.email,
                'office_name': user_profile.office_name or (latest_qpr.officeName if latest_qpr else 'Not Set'),
                'office_code': user_profile.office_code or (latest_qpr.officeCode if latest_qpr else 'Not Set'),
                'quarter': latest_qpr.quarter if latest_qpr else 'Not Set',
                'year': latest_qpr.year if latest_qpr else 'Not Set',
                'qpr_status': latest_qpr.status if latest_qpr else 'Not Submitted',
            })
        
        if user_details:
            hod_groups.append({
                'hod_name': hod_name,
                'hod_email': '-',
                'hod_emp_code': '-',
                'user_count': len(user_details),
                'users': user_details
            })
    
    # Also add users who are their own HOD (hod_name=None)
    own_hods = UserProfile.objects.filter(role='user', hod_name__isnull=True).order_by('user__first_name')
    for user_profile in own_hods:
        # Apply employee code filter
        if employee_code_filter and employee_code_filter.lower() not in user_profile.employee_code.lower():
            continue
        
        # Apply name filter
        if name_filter:
            user_name = user_profile.user.first_name or user_profile.name or user_profile.employee_code
            if name_filter.lower() not in user_name.lower():
                continue
        
        # Quarter filter doesn't apply to own HODs (they have no users)
        if quarter_filter:
            continue
        
        hod_groups.append({
            'hod_name': user_profile.user.first_name or user_profile.name or user_profile.employee_code,
            'hod_email': user_profile.user.email,
            'hod_emp_code': user_profile.employee_code,
            'user_count': 0,
            'users': []
        })
    
    # Get all unique quarters for the dropdown
    all_quarters = set()
    for qpr in QPRRecord.objects.values_list('quarter', flat=True).distinct():
        if qpr:
            all_quarters.add(qpr)
    all_quarters = sorted(list(all_quarters))
    
    # Get all unique years for the dropdown
    all_years = set()
    for qpr in QPRRecord.objects.values_list('year', flat=True).distinct():
        if qpr:
            all_years.add(qpr)
    all_years = sorted(list(all_years))
    
    context = {
        'hod_groups': hod_groups,
        'employee_code_filter': employee_code_filter,
        'name_filter': name_filter,
        'quarter_filter': quarter_filter,
        'year_filter': year_filter,
        'all_quarters': all_quarters,
        'all_years': all_years
    }
    return render(request, 'qpr/admin_employee_list.html', context)



@login_required
def user_office_form(request):
    """User can update their office name and code"""
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
    
    context = {
        'profile': profile
    }
    return render(request, 'qpr/user_office_form.html', context)



@login_required
def admin_create_hod(request):
    """Admin can create new HOD"""
    if request.user.profile.role != 'admin':
        messages.error(request, 'Access denied. Admin only.')
        return redirect('/')
    
    if request.method == 'POST':
        emp_code = request.POST.get('emp_code', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = '123456'  # Default password for all new HODs
        
        # Validate
        if not emp_code or not first_name or not email:
            messages.error(request, 'Employee code, name, and email are required')
            return render(request, 'admin_create_hod.html')
        
        # Check if employee code already exists
        if UserProfile.objects.filter(employee_code=emp_code).exists():
            messages.error(request, 'Employee code already exists')
            return render(request, 'admin_create_hod.html')
        
        # Check if user already exists
        if User.objects.filter(username=emp_code).exists():
            messages.error(request, 'Username already exists')
            return render(request, 'admin_create_hod.html')
        
        try:
            # Create user
            user = User.objects.create_user(
                username=emp_code,
                password=password,
                email=email,
                first_name=first_name
            )
            
            # Create or update HOD profile with hod_name set to first_name
            # Note: signal may have already created profile with role='user', so we update it
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'employee_code': emp_code,
                    'role': 'hod',
                    'hod_name': first_name,
                    'name': first_name,
                    'profile_updated': True
                }
            )
            
            # If profile already existed (created by signal as 'user'), update it to 'hod'
            if not created:
                profile.role = 'hod'
                profile.hod_name = first_name
                profile.name = first_name
                profile.profile_updated = True
                profile.employee_code = emp_code
                profile.save()
            
            messages.success(request, f'HOD {first_name} created successfully! Emp Code: {emp_code}, Default Password: 123456')
            return redirect('qpr_admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error creating HOD: {str(e)}')
    
    return render(request, 'qpr/admin_create_hod.html')


@login_required
def change_password(request):
    """Users, HODs, and Admin can change password"""
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')
        
        # Validate old password
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
            return redirect(
                'qpr_user_dashboard' if request.user.profile.role == 'user'
                else 'qpr_hod_dashboard' if request.user.profile.role == 'hod'
                else 'qpr_admin_dashboard'
            )
    
    return render(request, 'qpr/change_password.html')


# ==================== HOD MANAGEMENT (ADMIN ONLY) ====================

@csrf_exempt
@login_required
def api_update_hod(request):
    """API endpoint to update HOD name and employee code (Admin only)"""
    if request.user.profile.role != 'admin':
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
            # Users under old HOD name should now reference new HOD name
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
@login_required
def report_list(request):
    return render(request, 'qpr/report_list.html')


@login_required
def report_detail(request, record_id):
    return render(request, 'qpr/report_detail.html', {
        'record_id': record_id
    })


