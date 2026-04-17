from multiprocessing import context
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from .templatetags.translate_tags import translate_text
import pandas as pd
import os
from datetime import date
from .models import FinancialYear
from django.conf import settings
from zoneinfo import ZoneInfo

    

QUARTERS = [
    ("30 जून / Jun 30", 6),
    ("30 सितंबर / Sep 30", 9),
    ("31 दिसंबर / Dec 31", 12),
    ("31 मार्च / Mar 31", 3),
]

def get_allowed_quarters(selected_year):
    today = timezone.localdate()
    current_start = today.year if today.month >= 4 else today.year - 1

    # Debug: record incoming year and computed current start
    print(f"[get_allowed_quarters] received selected_year={selected_year!r}, today={today}, current_start={current_start}")

    if not selected_year:
        selected_year = f"{current_start}-{current_start+1}"

    try:
        selected_start = int(selected_year.split('-')[0])
    except Exception as e:
        print(f"[get_allowed_quarters] failed to parse selected_year={selected_year!r}: {e}")
        return []

    if selected_start < current_start:
        return [q[0] for q in QUARTERS]

    if selected_start > current_start:
        print(f"[get_allowed_quarters] selected_start {selected_start} > current_start {current_start} -> returning []")
        return []

    month = today.month

    # Determine current quarter number based on server month using the same
    # mapping as the frontend: Apr-Jun -> 1, Jul-Sep -> 2, Oct-Dec -> 3, Jan-Mar -> 4
    if month <= 3:
        current_q = 4
    elif month <= 6:
        current_q = 1
    elif month <= 9:
        current_q = 2
    else:
        current_q = 3

    # Allow all quarters from start up to and including the current ongoing quarter
    # This keeps past quarters allowed, includes the ongoing quarter, and excludes future quarters.
    allowed = [q[0] for q in QUARTERS[:current_q]]

    # Defensive: if somehow allowed is empty for same-year, include first quarter
    if not allowed and selected_start == current_start:
        allowed = [QUARTERS[0][0]]

    print(f"[get_allowed_quarters] month={month}, current_q={current_q}, allowed_quarters={allowed}")
    return allowed

def get_current_financial_year():
    today = date.today()
    if today.month >= 4:
        start= today.year
    else:
        start= today.year - 1
    
    return start, start + 1

def ensure_current_financial_year():
    start, end = get_current_financial_year()

    FinancialYear.objects.get_or_create(
        start_year=start,
        end_year=end
    )

def send_system_email(user, request, email_type, extra_context=None, target_email=None):    
    if extra_context is None:
        extra_context = {}

    user_email = target_email or user.get_email()
    if not user_email: 
        return

    lang = request.session.get('lang', 'en') if request else 'en'
    if request:
        lang = request.session.get('lang', 'en')
    else:
        lang = extra_context.get('lang', 'en')
    
    domain = request.build_absolute_uri('/')[:-1] if request else ''
    raw_role = request.session.get('active_role', 'user').title() if request else 'User'
    translated_role = translate_text(raw_role, lang)
    configs = {
        'otp': {
            'subject': translate_text("Password Reset OTP", lang),
            'headline': translate_text("Verify Your Identity", lang),
            'body': translate_text("Your One-Time Password (OTP) is below. It is valid for 5 minutes.", lang),
            'details': {translate_text('OTP Code', lang): extra_context.get('otp')},
            'is_alert': True
        },
        'welcome': {
            'subject': "Welcome to Rajya Bhaasha!",
            'headline': "Welcome Aboard!",
            'body': "Your account has been created successfully. Your data is now encrypted and DPDP compliant.",
            'action_text': "Go to Dashboard",
            'action_url': f"{domain}{reverse('login')}"
        },
        'login': {
            'subject': "Security Alert: New Login",
            'headline': "New Login Detected",
            'body': "We noticed a new login to your account. If this was you, you can ignore this.",
            'details': {
                # Present the time in IST explicitly for security alerts
                'Time': timezone.now().astimezone(ZoneInfo("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M'),
                'Role': translated_role
            },
            'is_alert': True
        },
        'export': {
            'subject': "Data Export Initiated",
            'headline': "Data Export Alert",
            'body': "A copy of your personal data has been exported from your dashboard.",
            'details': {'Date': timezone.localtime().strftime('%Y-%m-%d')},
            'is_alert': True
        },
        'update': {
            'subject': "Account Updated",
            'headline': "Profile Updated",
            'body': "Your account information has been modified.",
            'action_text': "Check Profile",
            'action_url': f"{domain}{reverse('dashboard')}"
        },
        'reminder': {
            'subject': "Action Required: Complete Your Profile/QPR",
            'headline': "Pending Task Reminder",
            'body': "This is a reminder from your HOD. Please log in to complete your Profile and submit your Quarterly Progress Report (QPR) at the earliest.",
            'action_text': "Login Now",
            'action_url': f"{domain}{reverse('login')}"
        },
        'rejected_alert': {
            'subject': "Registration Status: Action Required",
            'headline': "Registration Rejected",
            'body': "Your recent registration request was rejected by your HOD. Please log in to update your personal details and employee information, or contact your administrator.",
            'action_text': "Update Profile",
            'action_url': f"{domain}{reverse('login')}",
            'is_alert': True
        },
        'accepted_alert': {
            'subject': "Registration Status: Action Required",
            'headline': "Registration Accepted",
            'body': "Your recent registration request has been accepted by your HOD. Please log in to update your personal details and employee information.",
            'action_text': "Update Profile",
            'action_url': f"{domain}{reverse('login')}",
            'is_alert': True
        },
        'manager_alert': {
            'subject': "Action Required: User Edit Request",
            'headline': "Edit Permission Requested",
            'body': extra_context.get('body_text', "A user has requested to edit their profile."),
            'action_text': "Review Request",
            'action_url': f"{domain}{reverse('manager_dashboard')}"
        },
        'reset': {
            'subject': "Password Changed",
            'headline': "Password Updated",
            'body': "Your password was successfully changed. If you did not do this, contact support immediately.",
            'is_alert': True
        },
        'freeze': {
    'subject': "Security Alert: Your Account has been Frozen",
    'headline': "Account Access Restricted",
    'body': "For your security, your profile has been frozen. You will need manager approval for future modifications.",
    'details': {
        'Status': translate_text("Frozen", lang),
        'Time': timezone.now().astimezone(ZoneInfo("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M')
    },
    'is_alert': True
}
    }
    cfg = configs.get(email_type)
    if not cfg: return
    body_en = cfg.get('body') 
    body_hi = translate_text(body_en, 'hi')
    context = {
        'username': user.username,
        'body_en': body_en,
        'body_hi': body_hi,
        'current_lang': lang,
        'headline': cfg.get('headline'),
        'body_text': cfg.get('body'),
        'details': cfg.get('details'),
        'action_text': cfg.get('action_text'),
        'action_url': cfg.get('action_url'),
        'is_alert': cfg.get('is_alert', False),
    }
    
    subject = translate_text(cfg['subject'], lang)
    if email_type == 'login':
        template_name = 'email/login_notification_dual.html'
    else:
        template_name = 'email/unified_email.html'
    html_msg = render_to_string(template_name, context)
    plain_msg = strip_tags(html_msg)
    try:
        email = EmailMultiAlternatives(subject, plain_msg, settings.EMAIL_HOST_USER, [user_email])
        email.attach_alternative(html_msg, "text/html")    
        email.send(fail_silently=False)
        # Email sent successfully
    except Exception as e:
        print(f"--- SMTP Error: {e} ---")
EXCEL_PATH = os.path.join(settings.MEDIA_ROOT, "data", "tg_hod_officers_employee_report.xlsx")

def load_employee_data():
    df = pd.read_excel(EXCEL_PATH)

    employee_dict = {}

    for _, row in df.iterrows():
        empcode = str(int(row["Empcode"])).strip()
        empcode = empcode.replace(".0", "").strip()
        

        # clean name
        name = str(row["Name"]).strip()
        name = name.replace("Shri", "").replace("Ms.", "").replace("Ms", "").strip().upper()

        mobile = str(row["Mobile"]).strip()

        hindi_name = str(row["Name in Hindi"]).strip()
        designation = str(row["Designation"]).strip()
        

        employee_dict[empcode] = {
            "name": name,
            "hindi_name": hindi_name,
            "designation": designation,
            "mobile": mobile,
            "state": str(row.get("State", "")).strip(),
            "ip_number": str(row.get("IP Number", "")).strip()
        }

    return employee_dict
