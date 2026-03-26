from multiprocessing import context
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from .templatetags.translate_tags import translate_text
from datetime import date
from .models import FinancialYear

def send_system_email(user, request, email_type, extra_context=None):    
    if extra_context is None:
        extra_context = {}

    user_email = user.get_email()
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
            'body': translate_text("Your One-Time Password (OTP) is below. It is valid for 10 minutes.", lang),
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
                'Time': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'Role': translated_role
            },
            'is_alert': True
        },
        'export': {
            'subject': "Data Export Initiated",
            'headline': "Data Export Alert",
            'body': "A copy of your personal data has been exported from your dashboard.",
            'details': {'Date': timezone.now().strftime('%Y-%m-%d')},
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
        'Time': timezone.now().strftime('%Y-%m-%d %H:%M')
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

# financial year utils

def get_current_financial_year():
    today = date.today()

    if today.month >= 4:
        start = today.year
    else:
        start = today.year - 1

    return start, start + 1


def ensure_current_financial_year():
    start, end = get_current_financial_year()

    FinancialYear.objects.get_or_create(
        start_year=start,
        end_year=end
    )

QUARTERS = [
    ("30 जून / Jun 30", 6),
    ("30 सितंबर / Sep 30", 9),
    ("31 दिसंबर / Dec 31", 12),
    ("31 मार्च / Mar 31", 3),
]

def get_allowed_quarters(selected_year):
    today = timezone.localdate()

    current_start = today.year if today.month >= 4 else today.year - 1

    if not selected_year:
        selected_year = f"{current_start}-{current_start+1}"

    try:
        selected_start = int(selected_year.split('-')[0])
    except:
        return []

    if selected_start < current_start:
        return [q[0] for q in QUARTERS]

    if selected_start > current_start:
        return []

    allowed = []
    month = today.month

    for name, end_month in QUARTERS:
        if end_month == 3:
            if month <= 3:
                allowed.append(name)
        elif month >= end_month:
            allowed.append(name)

    return allowed