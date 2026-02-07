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
    # Try getting role from Session -> If missing, get from Database -> Default to 'user'
    role = request.session.get('active_role', request.user.role)
    
    # Refresh session if it was missing
    if 'active_role' not in request.session:
        request.session['active_role'] = role

    # Routing Logic
    if role == 'user':
        return render(request, "dashboard.html")
    elif role in ['manager', 'admin']:
        return redirect('manager_dashboard')
    elif role == 'backup_user':
        # Backup users usually stay on the main dashboard to see the download link
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
    # This includes archived users because they are still in the table
    users = CustomUser.objects.all().exclude(pk=request.user.pk).order_by('-date_joined')
    return render(request, 'manager_dashboard.html', {'users': users})

@user_passes_test(lambda u: u.is_authenticated and (u.role in ['manager', 'admin'] or u.is_superuser))
def manage_user_action(request, user_id, action):
    target_user = get_object_or_404(CustomUser, id=user_id)
    lang = request.session.get('lang', 'en')
    
    if request.user.role == 'manager' and target_user.role == 'admin':
        messages.error(request, translate_text("Managers cannot edit Admins.", lang))
        return redirect('manager_dashboard')

    # ARCHIVE
    if action == 'archive':
        archive_user_action(target_user.id)
        messages.success(request, translate_text("User archived (Access Disabled).", lang))
        return redirect('manager_dashboard')
    
    # RESTORE (Unarchive)
    elif action == 'unarchive':
        target_user.is_active = True      # Allow login again
        target_user.is_archived = False   # Remove archive flag
        target_user.save()
        messages.success(request, translate_text("User restored successfully.", lang))
        return redirect('manager_dashboard')

    # APPROVE EDIT
    elif action == 'approve':
        target_user.is_edit_allowed = True
        target_user.save()
        messages.success(request, translate_text("Edit permission granted.", lang))
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

'''@csrf_exempt
def translate_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            text = data.get("text", "")
            target = data.get("target", "hi")
            
            if not text or text == "-":
                return JsonResponse({"translated": text})
            
            # Note: GoogleTranslator requires an active internet connection
            translated = GoogleTranslator(source="auto", target=target).translate(text)
            return JsonResponse({"translated": translated})
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    return JsonResponse({"error": "Invalid request"}, status=400)'''
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