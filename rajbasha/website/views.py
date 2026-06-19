import csv
import hashlib
import io
import json
import logging
import os
import random
import re
import subprocess
import secrets
import json as _json

# Django / stdlib
from django.conf import settings
from django.utils.html import escape
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.views import View
from website.models import QPRFinalization
from .forms import ManagerQPRForm
from .forms import AdminQPRForm
from .forms import EmployeeMasterForm
from datetime import date, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

# Third-party
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from captcha.models import logger
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm

# Local App Imports
from .utils import (
    send_system_email, get_allowed_quarters,
    ensure_current_financial_year
)
from .employeeform import EmployeeForm
from .forms import (
    CustomLoginForm,
    CustomUserCreationForm
)
from .signals import User
from .static_event_service import (
    delete_event, get_all_events, update_event_meta,
    upload_event, upload_images_to_existing_event
)
from .templatetags.translate_tags import translate_text

from .models import (
    ArchivedUser, CertificateData, CodeManualStandardForms, CustomUser, DataAccessLog,
    EditRequest, Employee, EmployeeMaster, HindiPost, ManagerCertificate, ManagerRequest, MonthlyFill,
    MonthlySnapshot, ProfileChangeRequest, QPRPartTwo, QPRRecord, QuarterlyFill,
    QuarterlySnapshot, Role, Section1FilesData, Section2MeetingsData,
    Section3OfficialLanguagesData, Section4HindiLettersData,
    Section5EnglishRepliedHindiData, Section6IssuedLettersData,
    Section7NotingsData, Section8WorkshopsData,
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData,
    Section11SpecificAchievementsData, StaffHindiKnowledge,
    TranslationKnowledge, TypingStenographyKnowledge,
    UserProfile, WebsiteDetail, WeeklyFill, WeeklySnapshot, Employee, ManagerQPR, AdminQPR, Office
)
from website.models import OfficersWorkInHindi

logger = logging.getLogger(__name__)

# Font Registration
FONT_PATH = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'NIRMALA.TTF')
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('HindiFont', FONT_PATH))

#############################################################################################################################################################################################################################################################################################################

def reject_querystring_on_post(request):
    if request.method == 'POST' and request.GET:
        return HttpResponseBadRequest("POST parameters must be sent in the request body.")
    return None


def is_valid_empcode(value):
    return bool(re.fullmatch(r"[0-9]{1,20}", value or ""))

def get_employee_details_form(request):
    if request.method == "POST":
        empcode = request.POST.get('empcode', '').strip()
       
        if not empcode:
            return JsonResponse({'status': 'error', 'message': 'Employee code required'})
       
        try:
            master_employee = EmployeeMaster.objects.filter(empcode=empcode, is_active=True).first()

            if not master_employee:
                return JsonResponse({'status': 'error', 'message': 'Invalid Employee Code'})
           
            return JsonResponse({
                'status': 'success',
                'name': master_employee.name or '',
                'mobile': master_employee.mobile or '',
                'ip_number': master_employee.ip_number or '',
                'state': master_employee.state or '',
                'hindi_name': master_employee.hindi_name or '',
                'designation': master_employee.designation or '',
                'division': master_employee.division or '',
                'office_name': '',
                'email': '',
            })
       
        except Exception:
            logger.exception("Failed to get employee details")
            return JsonResponse({'status': 'error', 'message': 'Unable to retrieve employee details'})
   
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
@require_http_methods(["POST"])
def submit_profile_change_request(request):
    try:
        data = json.loads(request.body)
        reason = data.get('change_reason', '').strip()
        allowed_fields = {'email', 'alternate_email', 'designation', 'highest_exam','hod_name'}
        requested_fields = data.get('requested_fields') or []
        requested_fields = [
            field for field in requested_fields
            if isinstance(field, str) and field in allowed_fields
        ]

        if not reason:
            return JsonResponse({'success': False, 'message': 'Reason is required'})

        if not requested_fields:
            return JsonResponse({'success': False, 'message': 'Please select at least one field to edit.'})

        profile = getattr(request.user, 'profile', None)
        if (
            profile is None
            or not profile.profile_updated
            or profile.approval_status != 'approved'
            or request.user.is_edit_allowed
        ):
            return JsonResponse({
                'success': False,
                'message': 'Profile change requests are only allowed for locked, approved profiles.'
            }, status=403)

        hod_identifier = (profile.hod_name or "").strip()

        if not hod_identifier:
            return JsonResponse({
                'success': False,
                'message': 'HOD is not assigned to your profile.'
            })
        existing_request = ProfileChangeRequest.objects.filter(
            profile=profile,
            status='pending'
        ).first()

        if existing_request:
            return JsonResponse({
                'success': False,
                'message': 'You already have a pending request. Please wait for approval.'
            })
        hod_profile = UserProfile.objects.filter(
            Q(roles__name='hod') | Q(user__roles__name='hod'),
            Q(employee_code=hod_identifier) |
            Q(name__iexact=hod_identifier) |
            Q(hod_name__iexact=hod_identifier) |
            Q(user__username__iexact=hod_identifier)
        ).distinct().first()

        if not hod_profile:
            return JsonResponse({
                'success': False,
                'message': f'HOD "{hod_identifier}" not found in system. Please ensure your HOD has registered and is approved.'
            })
        ProfileChangeRequest.objects.create(
            profile=profile,
            change_reason=reason,
            requested_fields=requested_fields,
            hod=hod_profile.user,
            status='pending'
        )
        return JsonResponse({
            'success': True,
            'message': 'Change request submitted successfully. Awaiting HOD approval.'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})

    except Exception:
            logger.exception("Failed to handle login notification")
            return JsonResponse({'success': False, 'message': 'Unable to process request'})

def can_manage_events(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_staff or user.is_superuser:
        return True

    profile = getattr(user, 'profile', None)
    return (
        user.roles.filter(name__in=['manager', 'admin']).exists()
        or (profile and profile.roles.filter(name__in=['manager', 'admin']).exists())
    )

def require_event_manager(user):
    if not can_manage_events(user):
        raise PermissionDenied

def get_event_images(request, folder):
    require_event_manager(request.user)

    if request.method != 'POST':
        return JsonResponse({'images': []}, status=400)
   
    try:
        events = get_all_events()
        event = next((e for e in events if e['folder'] == folder), None)
       
        if not event:
            return JsonResponse({'images': []})
       
        return JsonResponse({'images': event['images']})
    except Exception:
        logger.exception("Failed to retrieve images")
        return JsonResponse({'images': [], 'error': 'Unable to retrieve images'})

def update_event_titles(request):
    require_event_manager(request.user)

    if request.method != 'POST':
        return redirect('admin_events_dashboard')
   
    folder = request.POST.get('folder')
    title_en = request.POST.get('title_en')
    title_hi = request.POST.get('title_hi')
   
   
    try:
        update_event_meta(folder, title_en, title_hi)
        messages.success(request, "Titles updated")
    except Exception:
        logger.exception("Failed to upload file")
        messages.error(request, 'Unable to upload file. Please try again.')
   
    return redirect('admin_events_dashboard')



@login_required
def admin_events_dashboard(request):
    require_event_manager(request.user)

    events = get_all_events()
    return render(request, "admin_events_dashboard.html", {"events": events})
 
 
@login_required
def admin_upload_event(request):
    require_event_manager(request.user)

    folder = request.GET.get("folder")
 
    if request.method == "POST":
        event_date   = request.POST.get("event_date")
        event_name   = request.POST.get("event_name")
        event_name_hi = request.POST.get("event_name_hi", "")
        images       = request.FILES.getlist("images")
 
        try:
            if folder:
                upload_images_to_existing_event(folder, images)
            else:
                upload_event(event_date, event_name, event_name_hi, images)
 
            return JsonResponse({"status": "success"})
 
        except Exception:
            logger.exception("Failed to upload event")
            return JsonResponse({"status": "error", "message": "Unable to upload event"})
 
    return render(request, "admin_upload_event.html", {"folder": folder})
 
 
@login_required
def admin_delete_event(request, folder):
    require_event_manager(request.user)

    try:
        delete_event(folder)
        messages.success(request, "Event deleted successfully")
    except Exception:
        logger.error("Failed to save snapshot.", exc_info=True)
        safe_error_msg = "Failed to delete event. Please try again."
        messages.error(request, safe_error_msg)
    return redirect("admin_events_dashboard")
 
 
@login_required
def admin_edit_event_titles(request):
    require_event_manager(request.user)
    if request.method == "POST":
        try:
            data     = json.loads(request.body)
            folder   = data.get("folder", "").strip()
            title_en = data.get("title_en", "").strip()
            title_hi = data.get("title_hi", "").strip()
 
            if not folder or not title_en:
                return JsonResponse({"status": "error", "message": "folder and title_en are required"})
 
            update_event_meta(folder, title_en, title_hi)
            return JsonResponse({"status": "success"})
 
        except Exception:
            logger.exception("Failed to edit event titles")
            return JsonResponse({"status": "error", "message": "Unable to update event"})
 
    return JsonResponse({"status": "error", "message": "POST only"})

@login_required
def set_thumbnail(request, folder):
    require_event_manager(request.user)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)
   
    try:
        data = json.loads(request.body)
        thumbnail = data.get('thumbnail')
       
        if not thumbnail:
            return JsonResponse({'status': 'error', 'message': 'Thumbnail filename required'})
       
        update_event_meta(folder, None, None, thumbnail=thumbnail)
       
        return JsonResponse({'status': 'success'})
    except Exception:
        logger.exception("Failed to get office list")
        return JsonResponse({'status': 'error', 'message': 'Unable to retrieve offices'})
   
def user_has_role(user, role_name):
    profile = getattr(user, 'profile', None)
    if isinstance(role_name, (list, tuple)):
        user_has = user.roles.filter(name__in=role_name).exists()
        profile_has = profile.roles.filter(name__in=role_name).exists() if profile else False
        return user_has or profile_has
    else:
        user_has = user.roles.filter(name=role_name).exists()
        profile_has = profile.roles.filter(name=role_name).exists() if profile else False
        return user_has or profile_has

def user_role(user):
    if user is None or not user.is_authenticated:
        return None
   
    priority_roles = ['admin', 'manager', 'hod', 'user', 'backup_user']
    profile = getattr(user, 'profile', None)
    for role in priority_roles:
        if user.roles.filter(name=role).exists():
            return role
        if profile and profile.roles.filter(name=role).exists():
            return role
    return None

def user_get_all_roles(user):
    if user is None or not user.is_authenticated:
        return []
    profile = getattr(user, 'profile', None)
    user_roles = set(user.roles.values_list('name', flat=True))
    profile_roles = set(profile.roles.values_list('name', flat=True)) if profile else set()
    return list(sorted(user_roles.union(profile_roles)))

def is_admin(user):
    return user.is_authenticated and user_has_role(user, 'admin')

def get_active_hods(office_code=None):
    hod_query = UserProfile.objects.filter(
        Q(roles__name='hod') | Q(user__roles__name='hod')
    ).select_related('user', 'employee').distinct()

    def serialize_hods(qs):
        items = []
        seen_values = set()
        for hod in qs.exclude(user__username__isnull=True).exclude(user__username=''):
            value = (hod.employee_code or getattr(hod.user, 'username', '') or '').strip()
            username = (getattr(hod.user, 'username', '') or '').strip()
            if not value:
                continue
            try:
                active_master_exists = EmployeeMaster.objects.filter(
                    empcode=int(value),
                    is_active=True,
                ).exists()
            except (TypeError, ValueError):
                active_master_exists = False
            if not active_master_exists:
                continue
            name = (
                (hod.name or '').strip()
                or (getattr(hod.employee, 'ename', '') or '').strip()
                or (hod.user.get_full_name() or '').strip()
                or username
            )
            if value in seen_values:
                continue
            seen_values.add(value)
            label = f"{name} ({value})" if name and name != value else value
            items.append({
                'value': value,
                'label': label,
                'name': name,
                'username': username,
            })
        items.sort(key=lambda item: item['label'].lower())
        return items

    if office_code:
        specific_hods = serialize_hods(hod_query.filter(office_code=office_code))
        if specific_hods:
            return specific_hods

    return serialize_hods(hod_query)

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

def get_current_quarter():
    m = date.today().month

    if m <= 3:
        return "31 मार्च / Mar 31"
    elif m <= 6:
        return "30 जून / Jun 30"
    elif m <= 9:
        return "30 सितंबर / Sep 30"
    else:
        return "31 दिसंबर / Dec 31"


def get_current_year_label():
    today = date.today()
    if today.month >= 4:
        start = today.year
    else:
        start = today.year - 1
    return f"{start}-{start+1}"


def get_quarter_end_dates():
    today = date.today()
    month = today.month
    year = today.year
   
    if month <= 3:
        current_end = date(year, 3, 31)
        next_end = date(year, 6, 30)
    elif month <= 6:
        current_end = date(year, 6, 30)
        next_end = date(year, 9, 30)
    elif month <= 9:
        current_end = date(year, 9, 30)
        next_end = date(year, 12, 31)
    else:
        current_end = date(year, 12, 31)
        next_end = date(year + 1, 3, 31)
   
    return {'current': current_end, 'next': next_end}


def get_base_year(year_label):
    return int(year_label.split("-")[0])

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

def _quarter_label_to_daterange(quarter_label, year_label) -> tuple[date, date]:
    try:
        base = get_base_year(year_label)
    except Exception:
        base = date.today().year
    q = (quarter_label or '').strip()
    if q.upper() == 'Q1' or 'Jun' in q or 'जून' in q:
        start = date(base, 4, 1)
        end = date(base, 6, 30)
    elif q.upper() == 'Q2' or 'Sep' in q or 'सितंबर' in q or 'सित' in q:
        start = date(base, 7, 1)
        end = date(base, 9, 30)
    elif q.upper() == 'Q3' or 'Dec' in q or 'दिसंबर' in q or 'दिस' in q:
        start = date(base, 10, 1)
        end = date(base, 12, 31)
    else:
        start = date(base+1, 1, 1)
        end = date(base+1, 3, 31)
    return (start, end)


def _quarter_query_values(quarter_label):
    q = (quarter_label or '').strip()
    normalized = q.upper()
    if normalized == 'Q1' or 'Jun' in q or 'जून' in q:
        return ['Q1', '30 जून / Jun 30']
    if normalized == 'Q2' or 'Sep' in q or 'सितंबर' in q or 'सित' in q:
        return ['Q2', '30 सितंबर / Sep 30']
    if normalized == 'Q3' or 'Dec' in q or 'दिसंबर' in q or 'दिस' in q:
        return ['Q3', '31 दिसंबर / Dec 31']
    if normalized == 'Q4' or 'Mar' in q or 'मार्च' in q:
        return ['Q4', '31 मार्च / Mar 31']
    return [q] if q else []


def get_clipped_week_bounds(date_val, quarter_label, year_label):
    weekday = date_val.weekday()
    week_start = date_val - timedelta(days=weekday)
    week_end = week_start + timedelta(days=5)
    q_start, q_end = _quarter_label_to_daterange(quarter_label, year_label)
    clipped_start = max(week_start, q_start)
    clipped_end = min(week_end, q_end)
   
    return (clipped_start, clipped_end)


NUMERIC_KEYS = [
    's1_total','s1_hindi','s2_meetings','s2_minutes','s2_papers_total','s2_papers_hindi',
    's3_total','s3_bilingual','s3_english','s3_hindi_only',
    's4_total','s4_no_reply','s4_replied_hindi','s4_replied_eng',
    's5_total','s5_hindi','s5_english','s5_noreply',
    's6_a_hindi','s6_a_eng','s6_a_total','s6_b_hindi','s6_b_eng','s6_b_total','s6_c_hindi','s6_c_eng','s6_c_total',
    's7_hindi','s7_eng','s7_total','s7_eoffice',
    's8_workshops','s8_officers','s8_employees'
]


def _serialize_managerqpr(m):
    out = {k: 0 for k in NUMERIC_KEYS}
    if not m:
        return out
    try:
        out['s2_meetings'] = int(getattr(m, 's2_meetings_count', 0) or 0)
        out['s2_minutes'] = int(getattr(m, 's2_hindi_minutes', 0) or 0)
        out['s2_papers_total'] = int(getattr(m, 's2_total_papers', 0) or 0)
        out['s2_papers_hindi'] = int(getattr(m, 's2_hindi_papers', 0) or 0)

        out['s4_total'] = int(getattr(m, 's4_total_letters', 0) or 0)
        out['s4_no_reply'] = int(getattr(m, 's4_no_reply_letters', 0) or 0)
        out['s4_replied_hindi'] = int(getattr(m, 's4_replied_hindi_letters', 0) or 0)
        out['s4_replied_eng'] = int(getattr(m, 's4_replied_english_letters', 0) or 0)

        out['s5_total'] = int(getattr(m, 's5_region_a_english_letters', 0) or 0)
        out['s5_hindi'] = int(getattr(m, 's5_region_a_replied_hindi', 0) or 0)
        out['s5_english'] = int(getattr(m, 's5_region_a_replied_english', 0) or 0)
        out['s5_noreply'] = int(getattr(m, 's5_region_a_no_reply', 0) or 0)

        out['s6_a_hindi'] = int(getattr(m, 's6_region_a_hindi_bilingual', 0) or 0)
        out['s6_a_eng'] = int(getattr(m, 's6_region_a_english_only', 0) or 0)
        out['s6_a_total'] = int(getattr(m, 's6_region_a_total', 0) or 0)
        out['s6_b_hindi'] = int(getattr(m, 's6_region_b_hindi_bilingual', 0) or 0)
        out['s6_b_eng'] = int(getattr(m, 's6_region_b_english_only', 0) or 0)
        out['s6_b_total'] = int(getattr(m, 's6_region_b_total', 0) or 0)
        out['s6_c_hindi'] = int(getattr(m, 's6_region_c_hindi_bilingual', 0) or 0)
        out['s6_c_eng'] = int(getattr(m, 's6_region_c_english_only', 0) or 0)
        out['s6_c_total'] = int(getattr(m, 's6_region_c_total', 0) or 0)

        out['s7_hindi'] = int(getattr(m, 's7_hindi_pages', 0) or 0)
        out['s7_eng'] = int(getattr(m, 's7_english_pages', 0) or 0)
        out['s7_total'] = int(getattr(m, 's7_total_pages', 0) or 0)
        out['s7_eoffice'] = int(getattr(m, 's7_eoffice_notings', 0) or 0)

        out['s8_workshops'] = int(getattr(m, 's8_full_day_workshops', 0) or 0)
        out['s8_officers'] = int(getattr(m, 's8_officers_trained', 0) or 0)
        out['s8_employees'] = int(getattr(m, 's8_employees_trained', 0) or 0)
    except Exception:
        pass
    return out


def _serialize_adminqpr(a):
    out = {k: 0 for k in NUMERIC_KEYS}
    if not a:
        return out
    try:
        out['s2_meetings'] = int(getattr(a, 'a_s2_meetings_count', 0) or 0)
        out['s2_minutes'] = int(getattr(a, 'a_s2_hindi_minutes', 0) or 0)
        out['s2_papers_total'] = int(getattr(a, 'a_s2_total_papers', 0) or 0)
        out['s2_papers_hindi'] = int(getattr(a, 'a_s2_hindi_papers', 0) or 0)

        out['s3_total'] = int(getattr(a, 'a_s3_total_documents', 0) or 0)
        out['s3_bilingual'] = int(getattr(a, 'a_s3_bilingual_documents', 0) or 0)
        out['s3_english'] = int(getattr(a, 'a_s3_english_only_documents', 0) or 0)
        out['s3_hindi_only'] = int(getattr(a, 'a_s3_hindi_only_documents', 0) or 0)

        out['s4_total'] = int(getattr(a, 'a_s4_total_letters', 0) or 0)
        out['s4_no_reply'] = int(getattr(a, 'a_s4_no_reply_letters', 0) or 0)
        out['s4_replied_hindi'] = int(getattr(a, 'a_s4_replied_hindi_letters', 0) or 0)
        out['s4_replied_eng'] = int(getattr(a, 'a_s4_replied_english_letters', 0) or 0)

        out['s7_hindi'] = int(getattr(a, 'a_s7_hindi_pages', 0) or 0)
        out['s7_eng'] = int(getattr(a, 'a_s7_english_pages', 0) or 0)
        out['s7_total'] = int(getattr(a, 'a_s7_total_pages', 0) or 0)
        out['s7_eoffice'] = int(getattr(a, 'a_s7_eoffice_notings', 0) or 0)
    except Exception:
        pass
    return out

def _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='daily'):
    total = {k: 0 for k in NUMERIC_KEYS}
    if not start_dt or not end_dt:
        return total
    qs = QPRRecord.objects.filter(
        user=user,
        is_submitted=True,
        frequency__iexact=(source_frequency or '')
    )

    for r in qs:
        try:
            r_start = getattr(r, 'period_start', None)
            r_end = getattr(r, 'period_end', None)
            if r_start and not r_end:
                freq = (getattr(r, 'frequency', '') or '').lower()
                if freq == 'daily':
                    r_end = r_start
                elif freq == 'weekly':
                    r_end = r_start + timedelta(days=5)
                elif freq == 'monthly':
                    y, m = r_start.year, r_start.month
                    if m == 12:
                        r_end = date(y, 12, 31)
                    else:
                        r_end = date(y, m + 1, 1) - timedelta(days=1)
                elif freq == 'quarterly':
                    try:
                        q_s, q_e = _quarter_label_to_daterange(getattr(r, 'quarter', None), getattr(r, 'year', None))
                        r_start = r_start or q_s
                        r_end = r_end or q_e
                    except Exception:
                        r_end = r_start
                else:
                    r_end = r_start

            if not r_start and r_end:
                r_start = r_end

            if not r_start and not r_end:
                created = getattr(r, 'created_at', None)
                if created:
                    r_start = created.date()
                    r_end = r_start
                else:
                    continue

            if r_start <= end_dt and r_end >= start_dt:
                try:
                    data = serialize_qpr_record(r)
                except Exception:
                    continue

                for k in NUMERIC_KEYS:
                    v = data.get(k)
                    if v is None or v == '':
                        continue
                    try:
                        total[k] += int(v)
                    except Exception:
                        continue
        except Exception:
            continue

    return total


def _aggregate_records_with_fallback(user, start_dt, end_dt, preferred='daily'):
    pref = (preferred or '').lower()

    def _has_nonzero(tot):
        return any((tot.get(k, 0) or 0) != 0 for k in NUMERIC_KEYS)

    if pref == 'daily':
        try:
            return _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='daily')
        except Exception:
            return {k: 0 for k in NUMERIC_KEYS}

    if pref == 'weekly':
        try:
            totals = _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='weekly')
        except Exception:
            totals = {k: 0 for k in NUMERIC_KEYS}
        if _has_nonzero(totals):
            return totals
        try:
            return _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='daily')
        except Exception:
            return {k: 0 for k in NUMERIC_KEYS}

    if pref == 'monthly':
        try:
            monthly_tot = _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='monthly')
        except Exception:
            monthly_tot = {k: 0 for k in NUMERIC_KEYS}
        if _has_nonzero(monthly_tot):
            return monthly_tot

        acc = {k: 0 for k in NUMERIC_KEYS}
        w_start = start_dt - timedelta(days=start_dt.weekday())
        cur = w_start
        while cur <= end_dt:
            week_start = cur
            week_end = cur + timedelta(days=5)
            actual_start = max(week_start, start_dt)
            actual_end = min(week_end, end_dt)
            if actual_start <= actual_end:
                try:
                    wtot = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='weekly')
                except Exception:
                    wtot = {k: 0 for k in NUMERIC_KEYS}
                if not _has_nonzero(wtot):
                    try:
                        wtot = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='daily')
                    except Exception:
                        wtot = {k: 0 for k in NUMERIC_KEYS}
                for k in NUMERIC_KEYS:
                    acc[k] += int(wtot.get(k, 0) or 0)
            cur = cur + timedelta(days=7)
        return acc

    try:
        qtot = _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='quarterly')
    except Exception:
        qtot = {k: 0 for k in NUMERIC_KEYS}
    if _has_nonzero(qtot):
        return qtot

    acc = {k: 0 for k in NUMERIC_KEYS}
    m = start_dt
    while m <= end_dt:
        month_start = date(m.year, m.month, 1)
        if m.month == 12:
            month_end = date(m.year, 12, 31)
        else:
            month_end = date(m.year, m.month + 1, 1) - timedelta(days=1)
        if month_end > end_dt:
            month_end = end_dt
        if month_start < start_dt:
            month_start = start_dt

        try:
            mtot = _aggregate_records_for_range(user, month_start, month_end, source_frequency='monthly')
        except Exception:
            mtot = {k: 0 for k in NUMERIC_KEYS}
        if _has_nonzero(mtot):
            for k in NUMERIC_KEYS:
                acc[k] += int(mtot.get(k, 0) or 0)
        else:
            w_start = month_start - timedelta(days=month_start.weekday())
            cur = w_start
            while cur <= month_end:
                week_start = cur
                week_end = cur + timedelta(days=5)
                actual_start = max(week_start, month_start)
                actual_end = min(week_end, month_end)
                if actual_start <= actual_end:
                    try:
                        wtot = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='weekly')
                    except Exception:
                        wtot = {k: 0 for k in NUMERIC_KEYS}
                    if not _has_nonzero(wtot):
                        try:
                            wtot = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='daily')
                        except Exception:
                            wtot = {k: 0 for k in NUMERIC_KEYS}
                    for k in NUMERIC_KEYS:
                        acc[k] += int(wtot.get(k, 0) or 0)
                cur = cur + timedelta(days=7)
        if m.month == 12:
            m = date(m.year + 1, 1, 1)
        else:
            m = date(m.year, m.month + 1, 1)

    return acc


def _quarterly_snapshot_totals_for_user(user, quarter, year):
    snapshot = QuarterlySnapshot.objects.filter(
        user=user,
        quarter=quarter,
        year=year
    ).first()
    if not snapshot:
        return {k: 0 for k in NUMERIC_KEYS}
    return {k: getattr(snapshot, k, 0) or 0 for k in NUMERIC_KEYS}


def _aggregate_section11_text_for_range(user, start_dt, end_dt, text_field_name, source_frequency='daily'):
    text_parts = []
    if not start_dt or not end_dt:
        return ''

    qs = QPRRecord.objects.filter(
        user=user,
        is_submitted=True
    )
    if source_frequency and str(source_frequency).lower() != 'all':
        qs = qs.filter(frequency__iexact=(source_frequency or ''))
    qs = qs.order_by('period_start', 'period_end', 'id')

    for r in qs:
        try:
            r_start = getattr(r, 'period_start', None)
            r_end = getattr(r, 'period_end', None)

            if r_start and not r_end:
                freq = (getattr(r, 'frequency', '') or '').lower()
                if freq == 'daily':
                    r_end = r_start
                elif freq == 'weekly':
                    r_end = r_start + timedelta(days=5)
                elif freq == 'monthly':
                    y, m = r_start.year, r_start.month
                    if m == 12:
                        r_end = date(y, 12, 31)
                    else:
                        r_end = date(y, m + 1, 1) - timedelta(days=1)
                elif freq == 'quarterly':
                    try:
                        q_s, q_e = _quarter_label_to_daterange(getattr(r, 'quarter', None), getattr(r, 'year', None))
                        r_start = r_start or q_s
                        r_end = r_end or q_e
                    except Exception:
                        r_end = r_start
                else:
                    r_end = r_start

            if not r_start and r_end:
                r_start = r_end

            if not r_start and not r_end:
                created = getattr(r, 'created_at', None)
                if created:
                    r_start = created.date()
                    r_end = r_start
                else:
                    continue

            if r_start <= end_dt and r_end >= start_dt:
                s11 = getattr(r, 'section11', None)
                if s11:
                    text_value = getattr(s11, text_field_name, '')
                    if text_value and text_value.strip():
                        text_parts.append(text_value.strip())
        except Exception:
            continue

    return '\n---\n'.join(text_parts)


def _get_quarter_range_for_date(dt) -> tuple[date, date]:
    m = dt.month
    y = dt.year
    if m in (4,5,6):
        return (date(y,4,1), date(y,6,30))
    if m in (7,8,9):
        return (date(y,7,1), date(y,9,30))
    if m in (10,11,12):
        return (date(y,10,1), date(y,12,31))
    # Jan-Mar
    return (date(y,1,1), date(y,3,31))


def _quarter_label_for_date(dt):
    if dt.month in (4, 5, 6):
        return '30 जून / Jun 30'
    if dt.month in (7, 8, 9):
        return '30 सितंबर / Sep 30'
    if dt.month in (10, 11, 12):
        return '31 दिसंबर / Dec 31'
    return '31 मार्च / Mar 31'


def _financial_year_for_date(dt):
    start = dt.year if dt.month >= 4 else dt.year - 1
    return f"{start}-{start + 1}"


def _last_working_before(d):
    while d.weekday() > 5:  # Sunday
        d = d - timedelta(days=1)
    return d


def _is_date_in_current_system_quarter(date_value, today=None):
    today = today or timezone.localdate()
    current_start, current_end = _get_quarter_range_for_date(today)
    return current_start <= date_value <= current_end


def _is_future_quarter(period_start, today=None):
    today = today or timezone.localdate()
    current_start, _ = _get_quarter_range_for_date(today)
    return period_start > current_start


def _current_quarter_fill_error(frequency):
    messages_by_frequency = {
        'weekly': 'Weekly QPR can be filled only after the working week is complete.',
        'monthly': 'Monthly QPR can be filled only on month end.',
        'quarterly': 'Quarterly QPR can be filled only on quarter end.'
    }
    return messages_by_frequency.get(
        frequency,
        'You can fill weekly, monthly, or quarterly QPR only on weekdays/month end/quarter end for the current quarter.'
    )


def _current_quarter_aggregate_fill_allowed(frequency, selected_date):
    if frequency == 'weekly':
        _, week_end = compute_period('weekly', selected_date=selected_date)
        return selected_date == week_end

    if frequency == 'monthly':
        _, month_end = compute_period('monthly', selected_date=selected_date)
        return selected_date == _last_working_before(month_end)

    if frequency == 'quarterly':
        _, quarter_end = _get_quarter_range_for_date(selected_date)
        return selected_date == _last_working_before(quarter_end)

    return True


def compute_period(frequency, selected_date=None, quarter=None, year=None):
    if selected_date is None:
        selected_date = timezone.localdate()

    if frequency == 'daily':
        return (selected_date, selected_date)

    if frequency == 'weekly':
        start = selected_date - timedelta(days=selected_date.weekday())
        end = start + timedelta(days=5)
        try:
            q_start, q_end = _get_quarter_range_for_date(selected_date)
            if start < q_start: start = q_start
            if end > q_end: end = q_end
        except Exception:
            pass
        return (start, end)

    if frequency == 'monthly':
        start = date(selected_date.year, selected_date.month, 1)
        if selected_date.month == 12:
            end = date(selected_date.year, 12, 31)
        else:
            end = date(selected_date.year, selected_date.month + 1, 1) - timedelta(days=1)
        try:
            q_start, q_end = _get_quarter_range_for_date(selected_date)
            if start < q_start: start = q_start
            if end > q_end: end = q_end
        except Exception:
            pass
        return (start, end)

    if frequency == 'quarterly':
        if quarter and year:
            try:
                return _quarter_label_to_daterange(quarter, year)
            except Exception:
                pass
        return _get_quarter_range_for_date(selected_date)

    return (selected_date, selected_date)


SNAPSHOT_EDIT_SCOPES = {'weekly', 'monthly', 'quarterly'}


def _snapshot_bounds_for_record(record, scope):
    scope = (scope or '').lower()
    if scope == 'weekly':
        return get_clipped_week_bounds(record.period_start, record.quarter, record.year)
    if scope == 'monthly':
        return compute_period('monthly', selected_date=record.period_start)
    if scope == 'quarterly':
        return _quarter_label_to_daterange(record.quarter, record.year)
    return (None, None)


def _snapshot_model_for_scope(scope):
    scope = (scope or '').lower()
    if scope == 'weekly':
        return WeeklySnapshot
    if scope == 'monthly':
        return MonthlySnapshot
    if scope == 'quarterly':
        return QuarterlySnapshot
    return None


def _snapshot_for_record(record, scope):
    model = _snapshot_model_for_scope(scope)
    ps, pe = _snapshot_bounds_for_record(record, scope)
    if not model or not ps or not pe:
        return None

    if scope == 'quarterly':
        snapshot, _ = model.objects.get_or_create(
            user=record.user,
            quarter=record.quarter,
            year=record.year,
            defaults={'period_start': ps, 'period_end': pe, 'is_overwritten': False}
        )
    else:
        snapshot, _ = model.objects.get_or_create(
            user=record.user,
            period_start=ps,
            period_end=pe,
            quarter=record.quarter,
            year=record.year,
            defaults={'is_overwritten': False}
        )
    return snapshot


def _snapshot_details(snapshot):
    return {key: getattr(snapshot, key, 0) or 0 for key in NUMERIC_KEYS}


def _overwrite_snapshot_from_details(record, scope, details):
    snapshot = _snapshot_for_record(record, scope)
    if not snapshot:
        return None

    for key in NUMERIC_KEYS:
        try:
            value = details.get(key, 0)
            setattr(snapshot, key, int(value or 0))
        except (TypeError, ValueError):
            setattr(snapshot, key, 0)
    snapshot.is_overwritten = True
    snapshot.overwritten_at = now()
    snapshot.save()
    return snapshot


def _approved_qpr_edit_request(user, record, scope='any'):
    if not user or not record:
        return None

    requests = EditRequest.objects.filter(
        user=user,
        request_type='qpr',
        qpr_record_id=record.pk,
        status='approved'
    ).order_by('-approved_at', '-updated_at')

    scope = (scope or 'any').lower()
    for edit_request in requests:
        requested_data = edit_request.requested_data or {}
        requested_scope = (requested_data.get('edit_scope') or '').lower()
        if scope == 'any':
            return edit_request
        if scope == 'base' and requested_scope not in SNAPSHOT_EDIT_SCOPES:
            return edit_request
        if scope in SNAPSHOT_EDIT_SCOPES and requested_scope == scope:
            return edit_request
    return None


def _add_qpr_edit_flags(record_dict, record, current_user, owner_user=None):
    owner_user = owner_user or getattr(record, 'user', None)
    is_owner = (
        getattr(current_user, 'id', None) is not None
        and getattr(owner_user, 'id', None) == getattr(current_user, 'id', None)
    )

    approved_request = None
    edit_approved = False
    approved_scope = ''
    if is_owner and getattr(record, 'is_submitted', False):
        approved_request = _approved_qpr_edit_request(owner_user, record)
        edit_approved = bool(approved_request)
        if approved_request:
            approved_scope = ((approved_request.requested_data or {}).get('edit_scope') or '').lower()

    record_dict['edit_approved'] = edit_approved
    record_dict['edit_approved_scope'] = approved_scope
    record_dict['can_edit'] = (
        is_owner
        and (
            not getattr(record, 'is_submitted', False)
            or (edit_approved and approved_scope not in SNAPSHOT_EDIT_SCOPES)
        )
    )
    record_dict['snapshot_can_edit'] = is_owner and edit_approved and approved_scope in SNAPSHOT_EDIT_SCOPES
    record_dict['has_pending_edit_request'] = EditRequest.objects.filter(
        user=owner_user,
        request_type='qpr',
        qpr_record_id=record.pk,
        status='pending'
    ).exists()
    return approved_request


def _refresh_parent_snapshots_after_overwrite(record, scope):
    scope = (scope or '').lower()
    if scope == 'weekly':
        month_start, month_end = compute_period('monthly', selected_date=record.period_start)
        monthly_snapshot = MonthlySnapshot.objects.filter(
            user=record.user,
            period_start=month_start,
            period_end=month_end,
            quarter=record.quarter,
            year=record.year
        ).first()
        if not monthly_snapshot or not getattr(monthly_snapshot, 'is_overwritten', False):
            _rebuild_monthly_snapshot_from_source(
                record.user, month_start, month_end, record.quarter, record.year
            )
        quarterly_snapshot = QuarterlySnapshot.objects.filter(
            user=record.user,
            quarter=record.quarter,
            year=record.year
        ).first()
        if not quarterly_snapshot or not getattr(quarterly_snapshot, 'is_overwritten', False):
            _rebuild_quarterly_snapshot_from_source(record.user, record.quarter, record.year)
    elif scope == 'monthly':
        quarterly_snapshot = QuarterlySnapshot.objects.filter(
            user=record.user,
            quarter=record.quarter,
            year=record.year
        ).first()
        if not quarterly_snapshot or not getattr(quarterly_snapshot, 'is_overwritten', False):
            _rebuild_quarterly_snapshot_from_source(record.user, record.quarter, record.year)


def _snapshot_edit_request_allowed(record, scope, today=None):
    scope = (scope or '').lower()
    if scope not in SNAPSHOT_EDIT_SCOPES:
        return True
    _, period_end = _snapshot_bounds_for_record(record, scope)
    if not period_end:
        return False
    today = today or timezone.localdate()
    return today >= period_end


def is_period_overlapping(user, start, end, exclude_id=None, new_frequency=None):
    if not start or not end:
        return False

    base_qs = QPRRecord.objects.filter(user=user, is_submitted=True)
    if exclude_id:
        base_qs = base_qs.exclude(pk=exclude_id)

    if not new_frequency:
        return base_qs.filter(period_start__lte=end, period_end__gte=start).exists()

    if str(new_frequency).lower() == 'weekly':
        non_daily_conflict = base_qs.exclude(frequency__iexact='daily').filter(period_start__lte=end, period_end__gte=start).exists()
        if non_daily_conflict:
            return True

        daily_count = base_qs.filter(frequency__iexact='daily', period_start__range=(start, end)).count()
        expected_days = 0
        d = start
        while d <= end:
            if d.weekday() <= 5:
                expected_days += 1
            d = d + timedelta(days=1)

        if expected_days > 0 and daily_count >= expected_days:
            return True

        return False

    if str(new_frequency).lower() == 'daily':
        return base_qs.filter(period_start__lte=end, period_end__gte=start).exists()

    if str(new_frequency).lower() == 'monthly':
        same_month_exists = base_qs.filter(
            frequency__iexact='monthly',
            period_start=start,
            period_end=end
        ).exists()
        if same_month_exists:
            return True

        quarterly_conflict = base_qs.filter(
            frequency__iexact='quarterly',
            period_start__lte=end,
            period_end__gte=start
        ).exists()
        return quarterly_conflict

    if str(new_frequency).lower() == 'quarterly':
        return base_qs.filter(
            frequency__iexact='quarterly',
            period_start=start,
            period_end=end
        ).exists()

    return base_qs.filter(period_start__lte=end, period_end__gte=start).exists()


def _allowed_frequencies_for_date(user, selected_date, allow_future_days=True):
    today = timezone.localdate()
    fy_start = today.year if today.month >= 4 else today.year - 1
    fiscal_start = date(fy_start, 4, 1)
    earliest = QPRRecord.objects.filter(user=user).order_by('period_start').first()
    if earliest and earliest.period_start:
        min_date = min(earliest.period_start, fiscal_start)
    else:
        min_date = fiscal_start

    if not allow_future_days:
        max_date = today
    else:
        try:
            if today.month == 12:
                next_month_year, next_month_month = today.year + 1, 1
            else:
                next_month_year, next_month_month = today.year, today.month + 1
           
            try:
                max_date = date(next_month_year, next_month_month, today.day)
            except ValueError:
                if next_month_month == 2:
                    max_date = date(next_month_year, 2, 29 if next_month_year % 4 == 0 else 28)
                elif next_month_month in [4, 6, 9, 11]:
                    max_date = date(next_month_year, next_month_month, 30)
                else:
                    max_date = date(next_month_year, next_month_month, 31)
        except Exception:
            max_date = today + timedelta(days=30)

    if selected_date < min_date:
        selected_date = min_date
    if selected_date > max_date:
        selected_date = max_date

    q_start, q_end = _get_quarter_range_for_date(selected_date)
    assert q_start is not None and q_end is not None

    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=5)

    week_start = max(week_start, q_start)
    week_end = min(week_end, q_end)
    week_days = [
    d for d in (week_start + timedelta(days=i) for i in range((week_end - week_start).days + 1))
    if d.weekday() <= 5 and q_start <= d <= q_end ]
    submitted_week = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='weekly', period_start__range=(week_start, week_end)).values_list('period_start', flat=True))
    missing_week = [d for d in week_days if d not in submitted_week and d >= min_date and d <= max_date]

    month_start = date(selected_date.year, selected_date.month, 1)
    if selected_date.month == 12:
        month_end = date(selected_date.year, 12, 31)
    else:
        month_end = date(selected_date.year, selected_date.month + 1, 1) - timedelta(days=1)
    month_days = [month_start + timedelta(days=i) for i in range((month_end - month_start).days + 1) if (month_start + timedelta(days=i)).weekday() <= 5]
    submitted_month = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='monthly', period_start__range=(month_start, month_end)).values_list('period_start', flat=True))
    missing_month = [d for d in month_days if d not in submitted_month and d >= min_date and d <= max_date]

    q_start, q_end = _get_quarter_range_for_date(selected_date)
    quarter_days = [q_start + timedelta(days=i) for i in range((q_end - q_start).days + 1) if (q_start + timedelta(days=i)).weekday() <= 5]
    submitted_quarter = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='quarterly', period_start__range=(q_start, q_end)).values_list('period_start', flat=True))
    missing_quarter = [d for d in quarter_days if d not in submitted_quarter and d >= min_date and d <= max_date]

    allowed = ['daily']
   
    month_last = _last_working_before(month_end)
    quarter_last = _last_working_before(q_end)
   
    if len(missing_week) > 0 and week_end <= today:
        allowed.append('weekly')
    if len(missing_month) > 0 and selected_date >= month_last:
        allowed.append('monthly')
    if len(missing_quarter) > 0 and selected_date >= quarter_last:
        allowed.append('quarterly')

    filtered_allowed = []
    for freq in allowed:
        ps, pe = compute_period(freq, selected_date=selected_date)
        if not is_period_overlapping(user, ps, pe, new_frequency=freq):
            filtered_allowed.append(freq)
    allowed = filtered_allowed

    return {
        'allowed': allowed,
        'missing_week': [d.isoformat() for d in missing_week],
        'missing_month': [d.isoformat() for d in missing_month],
        'missing_quarter': [d.isoformat() for d in missing_quarter],
        'min_date': min_date.isoformat(),
        'max_date': max_date.isoformat(),
        'default_date': timezone.localdate().isoformat()
    }


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
        's7_hindi': getattr(record.section7, 'hindi_pages', '') if hasattr(record, 'section7') else '',
        's7_eng': getattr(record.section7, 'english_pages', '') if hasattr(record, 'section7') else '',
        's7_total': getattr(record.section7, 'total_pages', '') if hasattr(record, 'section7') else '',
        's7_eoffice': getattr(record.section7, 'eoffice_notings', '') if hasattr(record, 'section7') else '',
        # Section 8
        's8_workshops': getattr(record.section8, 'full_day_workshops', '') if hasattr(record, 'section8') else '',
        's8_officers': getattr(record.section8, 'officers_trained', '') if hasattr(record, 'section8') else '',
        's8_employees': getattr(record.section8, 'employees_trained', '') if hasattr(record, 'section8') else '',
        # Section 9
        's9_date': getattr(record.section9, 'meeting_date', '') if hasattr(record, 'section9') else '',
        's9_sub_committees': getattr(record.section9, 'sub_committees_count', '') if hasattr(record, 'section9') else '',
        's9_meetings_count': getattr(record.section9, 'meetings_organized', '') if hasattr(record, 'section9') else '',
        's9_agenda_hindi': getattr(record.section9, 'agenda_hindi', '') if hasattr(record, 'section9') else '',
        # Section 10
        's10_date': getattr(record.section10, 'meeting_date', '') if hasattr(record, 'section10') else '',
        # Section 11
        's12_1': getattr(record.section11, 'innovative_work', '') if hasattr(record, 'section11') else '',
        's12_2': getattr(record.section11, 'special_events', '') if hasattr(record, 'section11') else '',
        's12_3': getattr(record.section11, 'hindi_medium_works', '') if hasattr(record, 'section11') else '',
        'details': {}
    }
    data['frequency'] = getattr(record, 'frequency', 'quarterly') if record else 'quarterly'
    data['period_start'] = getattr(record, 'period_start', None)
    data['period_end'] = getattr(record, 'period_end', None)
    data['is_quarterly_frozen'] = getattr(record, 'is_quarterly_frozen', False)
    try:
        for k in NUMERIC_KEYS:
            if data.get(k) is None or data.get(k) == '':
                data[k] = 0
    except Exception:
        pass
    try:
        details = {}
        for k in NUMERIC_KEYS:
            details[k] = data.get(k, 0)
        details['s9_date'] = data.get('s9_date', '')
        details['s10_date'] = data.get('s10_date', '')
        details['s12_1'] = data.get('s12_1', '')
        details['s12_2'] = data.get('s12_2', '')
        details['s12_3'] = data.get('s12_3', '')
        data['details'] = details
    except Exception:
        data['details'] = {}
    return data

def send_otp_email(user, lang, target_email=None, email_type='otp'):
    user.otp = str(secrets.randbelow(900000) + 100000)
    user.otp_created_at = timezone.now()
    user.save(update_fields=['otp', 'otp_created_at'])
    #send_system_email(user, None, email_type, extra_context={'otp': user.otp, 'lang': lang}, target_email=target_email)
    return user.otp


@require_POST
def custom_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')

def home(request):
    events = get_all_events()
    return render(request, "home.html", {"events": events})

def faqs(request):
    lang = request.session.get('lang', 'en')
    return render(request, "faqs.html", {"current_lang": lang})

def event_detail(request, folder):
    events = get_all_events()
    selected_event = next((e for e in events if e["folder"] == folder), None)

    if not selected_event:
        return redirect("home")

    return render(request, "event_detail.html", {"event": selected_event})

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
    
    # Get the list of roles we set up previously
    from .views import user_get_all_roles 
    roles = user_get_all_roles(request.user) 
    
    # Priority Routing: Drop them in the highest dashboard they have access to
    if 'admin' in roles:
        return redirect('qpr_admin_dashboard')
    elif 'hod' in roles:
        return redirect('qpr_hod_dashboard')
    elif 'manager' in roles:
        return redirect('manager_dashboard')
    elif 'backup_user' in roles:               
        return redirect('backup_user_dashboard')
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
        user = cast(CustomUser, form.get_user())
        current_lang = self.request.session.get('lang', 'en')
       
        #email_choice = form.cleaned_data.get('email_choice', 'primary')
        #target_email = user.get_email()
        #profile = getattr(user, 'profile', None)
        #alternate_email = getattr(profile, 'alternate_email', None)
       
        #if email_choice == 'alternate':
            #if alternate_email:
                #target_email = alternate_email
            #else:
                #messages.warning(self.request, translate_text("No alternate email found in your profile. Sending to official email.", current_lang))

        #send_otp_email(user, current_lang, target_email=target_email, email_type='login_otp')
       
        #self.request.session['pre_login_user_id'] = user.id
        #self.request.session['login_target_email'] = target_email
        #self.request.session['is_login_otp'] = True

        auth_login(self.request, user)
        try:
            # Rotate the session key; this is the recommended secure practice.
            self.request.session.cycle_key()
        except Exception:
            # If cycle_key is not supported by the session backend, ensure a new session is created.
            try:
                if not getattr(self.request.session, 'session_key', None):
                    self.request.session.create()
            except Exception:
                # best effort: ignore any session creation errors here
                pass

        self.request.session['lang'] = current_lang
        #self.request.session['active_role'] = active_role
        self.request.session.modified = True
        self.request.session.pop('pre_login_user_id',None)
        self.request.session.pop('login_target_email',None)
        self.request.session.pop('is_login_otp',None)
       
        #messages.success(self.request, translate_text("OTP sent successfully.", current_lang))
        #return redirect('verify_otp')
        return super().form_valid(form)

    def form_invalid(self, form):
        username = form.data.get('username')
        user = CustomUser.objects.filter(username=username).first()
        raw_password = form.data.get('password')
        if not isinstance(raw_password, str):
            return super().form_invalid(form)

        if user and not user.is_active and user.check_password(raw_password):
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

            employee_code = request.POST.get('employee_code', '').strip()
            phone = request.POST.get('phone', '').strip()

            otp = str(secrets.randbelow(900000) + 100000)
            signup_data = {
                'username': user.username,
                'email': form.cleaned_data['email'],
                'password': user.password,
                'first_name': user.first_name,
                'otp': otp,
                'otp_time': timezone.now().timestamp()
            }
            request.session['signup_data'] = signup_data
            request.session['is_signup'] = True

            #send_system_email(user, request, 'otp', extra_context={'otp': otp, 'lang': lang})

            messages.success(request, "Account verification initiated! Please verify your email with the OTP sent.")
            return redirect('verify_otp')
        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, 'registration/signup.html', {'form': form})

class LoginOTPView(View):
    def get(self, request):
        user_id = request.session.get('pre_otp_user_id')
        if not user_id:
            return redirect('login')
           
        user = CustomUser.objects.get(id=user_id)
        profile = getattr(user, 'profile', None)
        lang = request.session.get('lang', 'en')
       
        def mask_email(email):
            if not email or '@' not in email: return ""
            parts = email.split('@')
            return f"{parts[0][0]}***@{parts[1]}"
           
        context = {
            'primary_email': mask_email(user.get_email()),
            'has_alternate': bool(profile and profile.alternate_email),
            'alternate_email': mask_email(profile.alternate_email) if profile and profile.alternate_email else "",
            'current_lang': lang
        }
        return render(request, 'registration/verify_otp.html', context)
       
    def post(self, request):
        user_id = request.session.get('pre_otp_user_id')
        if not user_id:
            return redirect('login')
           
        user = CustomUser.objects.get(id=user_id)
        profile = getattr(user, 'profile', None)
        action = request.POST.get('action')
        lang = request.session.get('lang', 'en')
       
        if action == 'send_otp':
            email_choice = request.POST.get('email_choice', 'primary')
            target_email = user.get_email()
            if email_choice == 'alternate' and profile and profile.alternate_email:
                target_email = profile.alternate_email
               
            send_otp_email(user, lang, target_email=target_email)
            messages.success(request, translate_text("OTP sent to your selected email.", lang))
            return redirect('login_otp_step')
           
        elif action == 'verify_otp':
            otp_input = request.POST.get('otp', '').strip()
            magic_otp = '123456' ##bba testing
           
            is_real_otp_valid = (
                user.otp and
                user.otp == otp_input and
                user.otp_created_at and
                (timezone.now() - user.otp_created_at).total_seconds() < 300
            )
            if is_real_otp_valid or otp_input == magic_otp:  ##bba testing
                if is_real_otp_valid:
                    user.otp = None
                    user.save(update_fields=['otp'])
               
                auth_login(request, user)
               
                #send_system_email(user, request, 'login')
                if user_role(user) == 'user' and profile and not profile.profile_updated:
                    return redirect('qpr_user_profile')
                   
                request.session.pop('pre_otp_user_id', None)
                return redirect('dashboard')
            else:
                messages.error(request, translate_text("Invalid or expired OTP.", lang))
                return redirect('login_otp_step')
        else:
            messages.error(request, translate_text("Invalid request.", lang))
            return redirect('login_otp_step')
class ForgotPasswordView(View):
    def dispatch(self, request, *args, **kwargs):
        # Strictly reject submission parameters sent inside a GET query string
        if request.method == 'GET' and 'username' in request.GET:
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['POST'], "Account recovery requests are strictly forbidden within a GET query string.")
        return super().dispatch(request, *args, **kwargs)
    def get(self, request):
        return render(request, 'registration/forgot_password.html')
    def post(self, request):
        request.session.pop('is_signup', None)
        request.session.pop('signup_data', None)
        lang = request.session.get('lang', 'en')
        username = request.POST.get('username', '').strip()
        user = CustomUser.objects.filter(username=username).first()
        if user:
            send_otp_email(user, lang, email_type='reset_otp')
            email = user.get_email()
            if email:
                request.session['reset_email_hash'] = hashlib.sha256(email.encode()).hexdigest()
                messages.success(request, translate_text("OTP sent successfully.", lang))
                return redirect('verify_otp')
        messages.error(request, translate_text("User does not exist.", lang))
        return redirect('forgot_password')

class VerifyOTPView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash') and not request.session.get('is_signup') and not request.session.get('is_login_otp'):
            return redirect('forgot_password')
        lang = request.session.get('lang', 'en')
        context = {'title_text': translate_text("Verify OTP", lang), 'button_text': translate_text("Verify Code", lang), 'current_lang': lang}
        return render(request, 'registration/verify_otp.html', context)

    def post(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')

        otp_input = request.POST.get('otp', '').strip()
        lang = request.session.get('lang', 'en')
        if request.session.get('is_login_otp'):
            user_id = request.session.get('pre_login_user_id')
            if not user_id: return redirect('login')
            user = CustomUser.objects.get(id=user_id)
           
            att_key, blk_key = f"otp_att_login_{user_id}", f"otp_blk_login_{user_id}"
            if cache.get(blk_key):
                return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})
           
            magic_otp = '123456' ##bba testing
            if ((user.otp == otp_input and user.otp_created_at and (timezone.now() - user.otp_created_at).total_seconds() < 300) or otp_input == magic_otp ): ##bba testing
                user.otp = None
                user.save(update_fields=['otp'])
                auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                #send_system_email(user, request, 'login')
               
                request.session.pop('pre_login_user_id', None)
                request.session.pop('is_login_otp', None)
                request.session.pop('login_target_email', None)
               
                profile = getattr(user, 'profile', None)
                if user_role(user) == 'user' and profile and not profile.profile_updated:
                    return redirect('qpr_user_profile')
                return redirect('dashboard')
            else:
                attempts = cache.get(att_key, 0) + 1
                cache.set(att_key, attempts, 600)
                if attempts >= 5: cache.set(blk_key, True, 600)
                messages.error(request, translate_text("Invalid or expired OTP.", lang))
                return render(request, 'registration/verify_otp.html', {'current_lang': lang})
        elif request.session.get('is_signup'):
            signup_data = request.session.get('signup_data')
            if not signup_data:
                messages.error(request, "Session expired. Please sign up again.")
                return redirect('signup')
            email_hash = hashlib.sha256(signup_data['email'].encode()).hexdigest()
            att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
            if cache.get(blk_key):
                return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})  
            magic_otp = '123456' #bba testing
            if otp_input == signup_data['otp'] or otp_input == magic_otp: #bba testing
                if (timezone.now().timestamp() - signup_data['otp_time']) < 300:
                    try:
                        with transaction.atomic():
                            user, created = CustomUser.objects.get_or_create(
                                username=signup_data['username'],
                                defaults={
                                    'first_name': signup_data.get('first_name', ''),
                                    'is_active': True,
                                    'consent_given_at': timezone.now()
                                }
                            )
                            user.password = signup_data['password']
                            user.set_email(signup_data['email'])
                            user.save()
                            profile, _ = UserProfile.objects.get_or_create(
                                user=user,
                                defaults={"employee_code": user.username}
                            )
                            profile.approval_status = 'pending'
                            profile.profile_updated = False
                            profile.save()
                        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        request.session['lang'] = lang
                        request.session['active_role'] = 'user'
                        #send_system_email(user, request, 'welcome')
                        request.session.pop('signup_data', None)
                        request.session.pop('is_signup', None)
                        messages.success(request, "Email verified! Account created successfully.")
                        return redirect('dashboard')
                    except Exception:
                        logger.error("Failed to register.", exc_info=True)
                        safe_error_msg = "An Registration error occurred while saving. Please try again."
                        messages.error(request, safe_error_msg)
                        return redirect('signup')
            attempts = cache.get(att_key, 0) + 1
            cache.set(att_key, attempts, 600)
            if attempts >= 5: cache.set(blk_key, True, 600)
            messages.error(request, translate_text("Invalid or expired OTP.", lang))
            return render(request, 'registration/verify_otp.html', {'current_lang': lang})
        elif request.session.get('reset_email_hash'):
            email_hash = request.session.get('reset_email_hash')
            att_key, blk_key = f"otp_att_{email_hash}", f"otp_blk_{email_hash}"
            if cache.get(blk_key):
                return render(request, 'registration/verify_otp.html', {'is_blocked': True, 'current_lang': lang})
            user = CustomUser.objects.filter(email_hash=email_hash).first()
            magic_otp = '123456' #bba testing
            if user and (user.otp == otp_input or otp_input == magic_otp): #bbatesting
                if user.otp_created_at and (timezone.now() - user.otp_created_at).total_seconds() < 300:
                    request.session['otp_verified'] = True
                    return redirect('reset_password')
            attempts = cache.get(att_key, 0) + 1
            cache.set(att_key, attempts, 600)
            if attempts >= 5: cache.set(blk_key, True, 600)
            messages.error(request, translate_text("Invalid or expired OTP.", lang))
            return render(request, 'registration/verify_otp.html', {'current_lang': lang})
           
        else:
            return redirect('login')

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
            #send_system_email(dummy_user, request, 'otp', extra_context={'otp': new_otp, 'lang': lang})
            messages.success(request, translate_text("New OTP sent.", lang))
            return redirect('verify_otp')
        if request.session.get('is_login_otp'):
            user_id = request.session.get('pre_login_user_id')
            target_email = request.session.get('login_target_email')
            if not user_id: return redirect('login')
            user = CustomUser.objects.get(id=user_id)
            send_otp_email(user, lang, target_email=target_email, email_type='login_otp')
            messages.success(request, translate_text("New OTP sent.", lang))
            return redirect('verify_otp')
        email_hash = request.session.get('reset_email_hash')
        if not email_hash: return redirect('forgot_password')
        user = CustomUser.objects.filter(email_hash=email_hash).first()
        if not user: return redirect('forgot_password')
        send_otp_email(user, lang, email_type='reset_otp')
        messages.success(request, translate_text("New OTP sent.", lang))
        return redirect('verify_otp')

class ResetPasswordView(View):
    def get(self, request):
        if not request.session.get('reset_email_hash'):
            return redirect('forgot_password')
        return render(request, 'registration/reset_password.html')

    def post(self, request):
        email_hash = request.session.get('reset_email_hash')
        pwd = request.POST.get('password')
        cfm = request.POST.get('confirm_password')
        if not email_hash:
            return redirect('forgot_password')
        if pwd == cfm:
            user = CustomUser.objects.filter(email_hash=email_hash).first()
            if user:
                user.set_password(pwd)
                user.otp = None
                user.save()
                #send_system_email(user, request, 'reset')
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

@login_required
def export_user_data(request):
    user = request.user
    #send_system_email(user, request, 'export')
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
   
    p.setFont("HindiFont", 16)
    p.drawString(50, height - 50, "DPDP Privacy Audit Report")
   
    y = height - 100
    logs = DataAccessLog.objects.all().order_by('-access_time')
   
    for log in logs:
        p.setFont("HindiFont", 10)
       
        log_text = f"{log.access_time.strftime('%Y-%m-%d')}: {log.accessed_by.username} accessed {log.target_user.username}"
        p.drawString(50, y, log_text)
       
        y -= 20
        if y < 50:
            p.showPage()
            p.setFont("HindiFont", 10)
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
    try:
        host = os.getenv("DB_HOST")
        db = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")

        if not all([host, db, db_user]):
            messages.error(request, "Database environment variables are missing.")
            return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
        timestamp = datetime.now().strftime("%d-%m-%Y_%H:%M")
        filename = f"~/backups/backup_{timestamp}.sql"
        cmd = [
            "ssh",
            f"kia-psql@{host}",
            f"pg_dump -U {db_user} {db} -f {filename}"
        ]
        subprocess.run(cmd, check=True)
        messages.success(request, f"Database backup created successfully at {filename}")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    except subprocess.CalledProcessError as e:
        messages.error(request, "Backup command failed on the remote server.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
    except Exception:
        logger.error("Failed to save snapshot.", exc_info=True)
        safe_error_msg = "An unexpected error occurred while saving the snapshot. Please try again."
        messages.error(request, safe_error_msg)
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

@login_required
@user_passes_test(is_admin)
def archive_user(request, user_id):  
    user_to_archive = get_object_or_404(CustomUser, id=user_id)
   
    if getattr(user_to_archive, 'id', None) == getattr(request.user, 'id', None):
        messages.error(request, "You cannot archive yourself.")
        return redirect('dashboard')

    empcode_val = None
    profile = getattr(user_to_archive, 'profile', None)
    if profile and getattr(profile, 'employee_code', None):
        try:
            empcode_val = int(profile.employee_code)
        except (TypeError, ValueError):
            empcode_val = None

    if empcode_val is None:
        try:
            empcode_val = int(user_to_archive.username)
        except (TypeError, ValueError):
            empcode_val = None

    employee = None
    if empcode_val is not None:
        employee = Employee.objects.filter(empcode=empcode_val).first()

    snapshot = {}
    if employee:
        snapshot = {
            "name": employee.ename,
            "designation": employee.designation,
            "status": employee.status,
            "last_updated": str(employee.lastupdate)
        }

    ArchivedUser.objects.create(
        username=user_to_archive.username,
        email_hash=user_to_archive.email_hash,
        encrypted_email_data=user_to_archive.encrypted_email_data,
        original_user_id=user_to_archive.pk,
        employee_snapshot=json.dumps(snapshot)
    )
   
    user_to_archive.is_active = False    
    user_to_archive.is_archived = True
    user_to_archive.save()

    messages.success(request, f"User {user_to_archive.username} has been archived successfully.")
    return redirect('dashboard')

@login_required
@user_passes_test(is_admin)
def unarchive_user(request, archive_id):
    archived_record = get_object_or_404(ArchivedUser, id=archive_id)
   
    try:
        user_to_restore = CustomUser.objects.get(id=archived_record.original_user_id)
        user_to_restore.is_active = True
        user_to_restore.is_archived = False
        user_to_restore.save()
       
        archived_record.delete()
       
        messages.success(request, f"User {user_to_restore.username} has been unarchived/restored.")
        return redirect('dashboard')
       
    except CustomUser.DoesNotExist:
        messages.error(request, "Original user record not found. Cannot restore.")
        return redirect('dashboard')
   
def _can_edit_profile(user, profile, pending_change_request=None):
    if user_has_role(user, ['manager', 'admin']):
        return True

    if profile is None:
        return True

    if not profile.profile_updated:
        return True

    if pending_change_request is not None:
        return False

    if getattr(profile, 'approval_status', None) == 'rejected':
        return True

    return profile.approval_status == 'approved' and user.is_edit_allowed


@login_required
def profile_view(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    profile = getattr(user, 'profile', None)
    scoped_profile_fields = {'email', 'alternate_email', 'designation', 'highest_exam', 'hod_name'}
    profile_approval_required = not user_has_role(user, ['manager', 'admin'])
   
    pending_change_request = ProfileChangeRequest.objects.filter(
        profile=profile,
        status='pending'
    ).first() if profile and profile_approval_required else None

    approved_change_request = ProfileChangeRequest.objects.filter(
        profile=profile,
        status='approved'
    ).order_by('-approved_at').first() if profile and profile_approval_required else None

    can_edit = _can_edit_profile(user, profile, pending_change_request)
    approved_fields = []
    if approved_change_request:
        approved_fields = [
            field for field in (approved_change_request.requested_fields or [])
            if field in scoped_profile_fields
        ]

    is_approved = profile and profile.approval_status == "approved"

    if request.method == 'GET':
            forbidden_form_params = {
                'csrfmiddlewaretoken', 'empcode', 'username', 'email', 'phone', 
                'alternate_email', 'hname', 'ename', 'designation', 'super_annuation_date'
            }
            # Only reject if the GET request contains actual hidden form payload fields
            if any(param in request.GET for param in forbidden_form_params):
                return HttpResponseBadRequest("Bad Request: Form parameters are not allowed in the query string.")

    if request.method == 'POST':
        querystring_error = reject_querystring_on_post(request)
        if querystring_error:
            return querystring_error

        if not can_edit:
            messages.error(request, "Your profile is locked. Please request edit permission.", extra_tags='danger')
            return redirect('profile')

        if approved_change_request:
            if not approved_fields:
                messages.error(request, "No approved profile fields are available to edit. Please submit a new change request.", extra_tags='danger')
                return redirect('profile')

            if 'alternate_email' in approved_fields:
                profile.alternate_email = request.POST.get('alternate_email', '').strip()
                profile.save(update_fields=['alternate_email'])

            if 'email' in approved_fields:
                new_email = request.POST.get('email', '').lower().strip()
                if not new_email:
                    messages.error(request, "Email is required.", extra_tags='danger')
                    return redirect('profile')
                user.set_email(new_email)
                user.save()
                profile.email = new_email
                profile.save(update_fields=['encrypted_email'])

            if 'hod_name' in approved_fields:
                hod_name_post = request.POST.get('hod_name', '').strip()
                if profile_approval_required and not hod_name_post:
                    messages.error(request, "HOD/Approver selection is required.")
                    return redirect('profile')
                profile.hod_name = hod_name_post
                profile.save(update_fields=['hod_name'])

            if 'designation' in approved_fields or 'highest_exam' in approved_fields:
                employee = Employee.objects.filter(empcode=profile.employee_code).first()
                if not employee:
                    messages.error(request, "Employee record not found. Please contact admin.")
                    return redirect('profile')

                update_fields = []
                if 'designation' in approved_fields:
                    employee.designation = request.POST.get('designation') or employee.designation
                    update_fields.append('designation')

                if 'highest_exam' in approved_fields:
                    employee.highest_exam = ",".join(request.POST.getlist("hindi_exam"))
                    update_fields.append('highest_exam')

                if update_fields:
                    employee.save(update_fields=update_fields)

            user.is_edit_allowed = False
            user.save(update_fields=['is_edit_allowed'])
            approved_change_request.status = 'completed'
            approved_change_request.save(update_fields=['status'])
            messages.success(request, "Approved profile changes saved successfully. Your profile is locked again.")
            return redirect('profile')

        empcode = request.POST.get('empcode', '').strip()
        username = request.POST.get('username', '').strip()
        phone = request.POST.get('phone', '').strip()
        if not empcode:
            messages.error(request, "Employee Code is required.")
            return redirect('profile')
        if not is_valid_empcode(empcode):
            messages.error(request, "Employee Code must be numeric and up to 20 digits.")
            return redirect('profile')
        if not username:
            messages.error(request, "Employee Name is required.")
            return redirect('profile')
        if not phone:
            messages.error(request, "Phone Number is required.")
            return redirect('profile')

        new_email = request.POST.get('email', '').lower().strip()
        if not new_email:
            messages.error(request, "Email is required.", extra_tags='danger')
            return redirect('profile')

        email_hash = hashlib.sha256(new_email.encode()).hexdigest()

        hod_name_post = request.POST.get('hod_name', '').strip()
        if not profile_approval_required and not hod_name_post:
            hod_name_post = "ADMIN"
        if profile_approval_required and not hod_name_post:
            messages.error(request, "HOD/Approver selection is required.")
            return redirect('profile')

        master_employee = EmployeeMaster.objects.filter(empcode=empcode, is_active=True).first()
        if not master_employee:
            messages.error(request, "Invalid Employee Code. Please enter a code available in the employee master table.")
            return redirect('profile')

        employee = Employee.objects.filter(empcode=empcode).first()
        form = EmployeeForm(request.POST, instance=employee)
        if not form.is_valid():
            error_messages = []
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                error_messages.append(f"{label}: {', '.join(errors)}")
            details = " ".join(error_messages)
            messages.error(request, f"Form validation failed. {details}", extra_tags='danger')
            return redirect('profile')

        with transaction.atomic():
            user.set_email(new_email)
            user.save()

            if not profile:
                profile = UserProfile(user=user)

            profile.employee_code = empcode
            profile.phone = phone or (master_employee.mobile or '').strip()
            profile.office_code = request.POST.get('office_code', '').strip()
            profile.office_name = request.POST.get('office_name', '').strip()
            profile.office_state = request.POST.get('office_state', '').strip() or (master_employee.state or '').strip()
            profile.email = new_email
            profile.language_region = request.POST.get('language_region', '')
            profile.hod_name = hod_name_post
            profile.ip_number = request.POST.get('ip_number', '').strip() or (master_employee.ip_number or '').strip()
            profile.alternate_email = request.POST.get('alternate_email', '').strip()

            if not profile_approval_required:
                profile.approval_status = "approved"
            elif profile.approval_status != "approved":
                profile.approval_status = "pending_admin" if hod_name_post == "ADMIN" else "pending"

            profile.profile_updated = True
            profile.save()

            emp_instance = form.save(commit=False)
            emp_instance.highest_exam = ",".join(request.POST.getlist("hindi_exam"))
            emp_instance.super_annuation_date = form.cleaned_data.get('super_annuation_date')
            emp_instance.empcode = empcode
            if not emp_instance.ename:
                emp_instance.ename = (master_employee.name or '').strip()
            if not emp_instance.hname:
                emp_instance.hname = (master_employee.hindi_name or '').strip()
            if not emp_instance.designation:
                emp_instance.designation = (master_employee.designation or '').strip() or emp_instance.designation
            emp_instance.save()
            if profile:
                profile.employee = emp_instance
                profile.save(update_fields=['employee'])

        if approved_change_request:
            approved_change_request.status = 'completed'
            approved_change_request.save()

        #send_system_email(user, request, 'update')
        if profile_approval_required:
            messages.success(request, "Profile submitted successfully! It is now awaiting HOD approval.")
        else:
            messages.success(request, "Profile saved successfully.")
        return redirect('profile')

    empcode = profile.employee_code if profile else None
    employee = Employee.objects.filter(empcode=empcode).first() if empcode else None
    form = EmployeeForm(instance=employee)
    current_office_code = profile.office_code if profile else "0012"
    super_annuation_date_value = ''
    if employee:
        decrypted_super_annuation_date = employee.get_super_annuation_date()
        if decrypted_super_annuation_date:
            super_annuation_date_value = decrypted_super_annuation_date.strftime('%Y-%m-%d')

    offices = Office.objects.all()
    context = {
        'form': form,
        'employee': employee,
        'profile': profile,
        'offices': offices,
        'region_choices': QPRRecord.region_choices,
        'available_hods': get_active_hods(current_office_code),
        'current_hod': profile.hod_name if profile else None,
        'ip_number': profile.ip_number if profile else '',
        'alternate_email': profile.alternate_email if profile else '',
        'super_annuation_date_value': super_annuation_date_value,
        'can_edit': can_edit,
        'profile_approval_required': profile_approval_required,
        'profile_locked': not can_edit,
        'profile_approved': is_approved,
        'pending_change_request': pending_change_request,
        'has_pending_change_request': bool(pending_change_request),
        'has_approved_change_request': bool(approved_change_request),
        'approved_profile_fields': approved_fields,
        'approved_profile_fields_json': json.dumps(approved_fields),
        'profile_updated': profile.profile_updated if profile else False,
    }

    return render(request, 'profile.html', context)
@login_required
def approve_profile_change_hod(request, request_id):
    """HOD approves profile change request → unlock form"""

    if not user_has_role(request.user, ['hod', 'admin']):
        messages.error(request, "Unauthorized", extra_tags='danger')
        return redirect('qpr_hod_detail_list')

    change_request = get_object_or_404(ProfileChangeRequest, id=request_id)

    if change_request.status != 'pending':
        messages.warning(request, "This request is already processed.")
        return redirect('qpr_hod_detail_list')

    if change_request.hod != request.user and not request.user.is_staff:
        messages.error(request, "Not authorized for this request", extra_tags='danger')
        return redirect('qpr_hod_detail_list')

    change_request.status = 'approved'
    change_request.approved_at = timezone.now()
    change_request.save()
    user = change_request.profile.user
    user.is_edit_allowed = True
    user.save(update_fields=['is_edit_allowed'])

    messages.success(
        request,
        f"Edit request approved for {change_request.profile.name}. Form unlocked.",
        extra_tags='success'
    )

    return redirect('qpr_hod_detail_list')
@login_required
def reject_profile_change_hod(request, request_id):
    """HOD rejects profile change request → keep form locked"""

    if request.method != 'POST':
        return redirect('qpr_hod_detail_list')

    if not user_has_role(request.user, ['hod', 'admin']):
        messages.error(request, "Unauthorized", extra_tags='danger')
        return redirect('qpr_hod_detail_list')

    change_request = get_object_or_404(ProfileChangeRequest, id=request_id)

    if change_request.status != 'pending':
        messages.warning(request, "This request is already processed.")
        return redirect('qpr_hod_detail_list')

    if change_request.hod != request.user and not request.user.is_staff:
        messages.error(request, "Not authorized for this request", extra_tags='danger')
        return redirect('qpr_hod_detail_list')

    rejection_reason = request.POST.get('rejection_reason', '').strip()

    if not rejection_reason:
        messages.error(request, "Rejection reason is required", extra_tags='danger')
        return redirect('qpr_hod_detail_list')

    change_request.status = 'rejected'
    change_request.approved_at = timezone.now()
    change_request.approval_comments = rejection_reason
    change_request.save()

    user = change_request.profile.user
    user.is_edit_allowed = False
    user.save(update_fields=['is_edit_allowed'])

    messages.success(
        request,
        f"Edit request rejected for {change_request.profile.name}",
        extra_tags='success'
    )

    return redirect('qpr_hod_detail_list')

@login_required
def freeze_profile(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    user.is_frozen = True
    user.save()
    #send_system_email(user, request, 'freeze')
    messages.success(request, translate_text("Your profile has been frozen.", lang))
    return redirect('dashboard')

@login_required
def request_edit(request):
    lang = request.session.get('lang', 'en')
    user = request.user
    if not user.is_frozen: return redirect('dashboard')
   
    pending_request = EditRequest.objects.filter(
        user=request.user,
        request_type='profile',
        status='pending'
    ).exists()
   
    if pending_request:
        messages.warning(request, translate_text("You already have a pending profile edit request.", lang))
    else:
        profile = getattr(request.user, 'profile', None)
        hod_name = profile.hod_name if profile else None
        manager_user = None
        if hod_name:
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
            msg = f"User {user.username} has requested permission to edit their profile."
            #send_system_email(manager_user, request, 'manager_alert', extra_context={'body_text': msg})
        else:
            EditRequest.objects.create(
                user=request.user,
                request_type='profile',
                requested_data={'reason': 'User requested permission to edit profile'},
                reason='User requested permission to edit frozen profile',
                status='pending'
            )
            messages.success(request, translate_text("Profile edit request sent to admin for approval.", lang))
            admin = CustomUser.objects.filter(roles__name='admin').first()
            if admin:
                msg = f"User {user.username} has requested permission to edit their profile."
                #send_system_email(admin, request, 'manager_alert', extra_context={'body_text': msg})
   
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

@login_required
def user_dashboard(request):
    """User Dashboard View - Unified"""
    profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"employee_code": f"EMP{getattr(request.user, 'id', '')}"}
    )
    profile.refresh_from_db()
    if not profile.profile_updated:
        return redirect('qpr_user_profile')
    qpr_records = QPRRecord.objects.filter(user=request.user)
    today = timezone.localdate()
    submitted_qprs = QPRRecord.objects.filter(user=request.user, is_submitted=True, frequency__iexact='daily', period_start=today).count()
   
    available_hods = get_active_hods(profile.office_code)
   
    is_hod_or_manager = user_has_role(request.user, ['hod', 'manager'])
    roles = set(user_get_all_roles(request.user))
    roles_up = {r.upper() for r in roles}
    has_user = 'USER' in roles_up
    has_manager = 'MANAGER' in roles_up
    has_admin = 'ADMIN' in roles_up
    has_hod = 'HOD' in roles_up

    disable_user_dashboard_actions = (
        has_user and (has_manager or has_admin) and (not has_hod)
    )

    context = {
        'role': 'user',
        'profile': profile,
        'profile_status': 'Updated' if profile.profile_updated else 'Needs Update',
        'qpr_submitted': submitted_qprs > 0,
        'qpr_count': qpr_records.count(),
        'user': request.user,
        'available_hods': available_hods,
        'current_hod': profile.hod_name or '',
        'is_hod_or_manager': is_hod_or_manager,
        'disable_user_dashboard_actions': disable_user_dashboard_actions,
        'has_manager': has_manager,
        'has_admin': has_admin,
    }
    response = render(request, 'dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@login_required
def manager_qpr_view(request, id=None):
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden("Manager role required")

    if request.method == 'GET':
        forbidden_keys = {
            's1_total_files', 's2_meetings_count', 's9_agenda_hindi', 'form_type',
            's2_minutes', 's2_papers_total', 's2_papers_hindi', 's9_meetings_organized',
            # Additional structural/layout keys forbidden in GET
            'details', 'snapshot_edit_scope'
        }
        if any(k in request.GET for k in forbidden_keys):
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['POST'], "Form structural parameters are forbidden inside a GET query string.")

    instance = None
    if id:
        instance = get_object_or_404(ManagerQPR, pk=id)

    if request.method == 'POST':
        
        if instance:
            form = ManagerQPRForm(request.POST, instance=instance)
        else:
            form = ManagerQPRForm(request.POST)

        if form.is_valid():
            quarter = form.cleaned_data.get('quarter')
            financial_year = form.cleaned_data.get('financial_year')
            if not instance and ManagerQPR.objects.filter(user=request.user, quarter=quarter, financial_year=financial_year).exists():
                messages.error(request, "Manager QPR for this quarter and financial year has already been filled.")
            else:
                obj = form.save(commit=False)
                obj.user = request.user
                obj.is_submitted = True
                obj.submitted_at = timezone.now()
                obj.save()
                messages.success(request, "Manager QPR saved successfully.")
                return redirect('manager_qpr_detail', id=obj.id)
    else:
        if instance:
            form = ManagerQPRForm(instance=instance)
        else:
            form = ManagerQPRForm()

    return render(request, 'qpr/manager_qpr_form.html', {'form': form, 'instance': instance})


@login_required
def manager_qpr_detail(request, id):
    obj = get_object_or_404(ManagerQPR, id=id)
    if obj.user != request.user and not (request.user.is_staff or user_has_role(request.user, 'admin')):
        return HttpResponseForbidden()

    form = ManagerQPRForm(instance=obj)
    for name in form.fields:
        try:
            form.fields[name].widget.attrs['disabled'] = 'disabled'
        except Exception:
            pass

    return render(request, 'qpr/manager_qpr_form.html', {'form': form, 'instance': obj, 'readonly': True})


@login_required
def manager_section11_select_texts(request, manager_qpr_id=None):
    """Manager selects which users' Section 11 texts to include in their aggregated report."""
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden("Manager role required")

    manager_office = getattr(request.user.profile, 'office_code', None)
    if not manager_office:
        messages.error(request, "Your profile doesn't have an office code configured.")
        return redirect('manager_qpr_list')

    def resolve_user_identity(user):
        """Return a stable display name and employee code for Section 11 attribution."""
        profile = getattr(user, 'profile', None)
        employee_code = (
            (getattr(profile, 'employee_code', '') or '').strip()
            or (getattr(user, 'username', '') or '').strip()
        )

        employee = getattr(profile, 'employee', None) if profile else None
        if not employee and employee_code:
            try:
                employee = Employee.objects.filter(empcode=int(employee_code)).first()
            except (TypeError, ValueError):
                employee = None

        candidates = [
            getattr(profile, 'name', None) if profile else None,
            getattr(employee, 'ename', None) if employee else None,
            user.get_full_name() if hasattr(user, 'get_full_name') else None,
        ]
        display_name = ''
        for candidate in candidates:
            candidate = (candidate or '').strip()
            if candidate and candidate != employee_code:
                display_name = candidate
                break

        return {
            'display_name': display_name or employee_code or getattr(user, 'username', ''),
            'employee_code': employee_code or getattr(user, 'username', ''),
        }

    manager_qpr = None
    if manager_qpr_id:
        manager_qpr = get_object_or_404(ManagerQPR, pk=manager_qpr_id, user=request.user)

    quarter = manager_qpr.quarter if manager_qpr else None
    financial_year = manager_qpr.financial_year if manager_qpr else None
    try:
        quarter_start, quarter_end = _quarter_label_to_daterange(quarter, financial_year)
    except Exception:
        quarter_start, quarter_end = None, None

    def collect_user_section11(user):
        texts = {
            'innovative_work': '',
            'special_events': '',
            'hindi_medium_works': ''
        }
        latest_qpr = None

        if quarter_start and quarter_end:
            latest_qpr = QPRRecord.objects.filter(
                user=user,
                is_submitted=True,
                period_start__lte=quarter_end,
                period_end__gte=quarter_start
            ).order_by('-updated_at').first()

            for field_name in texts:
                texts[field_name] = _aggregate_section11_text_for_range(
                    user,
                    quarter_start,
                    quarter_end,
                    field_name,
                    source_frequency='all'
                )

        if not any(value.strip() for value in texts.values()) and quarter and financial_year:
            latest_qpr = QPRRecord.objects.filter(
                user=user,
                quarter__in=_quarter_query_values(quarter),
                year=financial_year,
                is_submitted=True
            ).order_by('-updated_at').first()

            if latest_qpr and hasattr(latest_qpr, 'section11'):
                s11 = latest_qpr.section11
                texts = {
                    'innovative_work': (s11.innovative_work or '').strip(),
                    'special_events': (s11.special_events or '').strip(),
                    'hindi_medium_works': (s11.hindi_medium_works or '').strip()
                }

        return texts, latest_qpr

    if request.method == 'POST':
        selected_user_ids = request.POST.getlist('selected_users')
       
        office_users = CustomUser.objects.filter(
            profile__office_code=manager_office,
            is_active=True
        ).exclude(id=request.user.id)
        texts_by_field = {
            'innovative_work': [],
            'special_events': [],
            'hindi_medium_works': []
        }

        for user_id in selected_user_ids:
            try:
                user_id = int(user_id)
                user = office_users.get(id=user_id)

                section11_texts, latest_qpr = collect_user_section11(user)
                if any(value.strip() for value in section11_texts.values()):
                    user_identity = resolve_user_identity(user)
                    user_display = user_identity['display_name']

                    for field_name, text_value in section11_texts.items():
                        if text_value:
                            texts_by_field[field_name].append(f"[{user_display}]: {text_value}")
            except (ValueError, CustomUser.DoesNotExist):
                continue

        aggregated_data = {
            'innovative_work': '\n\n'.join(texts_by_field['innovative_work']),
            'special_events': '\n\n'.join(texts_by_field['special_events']),
            'hindi_medium_works': '\n\n'.join(texts_by_field['hindi_medium_works'])
        }

        if manager_qpr:
            manager_qpr.s11_innovative_work = aggregated_data['innovative_work']
            manager_qpr.s11_special_events = aggregated_data['special_events']
            manager_qpr.s11_hindi_medium_works = aggregated_data['hindi_medium_works']
            manager_qpr.save()
            messages.success(request, "Section 11 texts aggregated and saved successfully.")
            return redirect('manager_qpr_detail', id=manager_qpr.id)
        else:
            request.session['section11_preview'] = aggregated_data
            messages.success(request, "Section 11 texts aggregated. Review below:")

    office_users = CustomUser.objects.filter(
        profile__office_code=manager_office,
        is_active=True
    ).exclude(id=request.user.id).select_related('profile', 'profile__employee')

    users_section11 = []

    for user in office_users:
        section11_texts, latest_qpr = collect_user_section11(user)
        if any(value.strip() for value in section11_texts.values()):
            user_identity = resolve_user_identity(user)
            users_section11.append({
                'user': user,
                'display_name': user_identity['display_name'],
                'employee_code': user_identity['employee_code'],
                'section11': section11_texts,
                'qpr': latest_qpr
            })

    context = {
        'manager_qpr': manager_qpr,
        'users_section11': users_section11,
        'manager_office': manager_office,
        'section11_preview': request.session.pop('section11_preview', None)
    }

    return render(request, 'qpr/manager_section11_select.html', context)



@login_required
def admin_qpr_view(request, id=None):
    if not user_has_role(request.user, 'admin'):
        return HttpResponseForbidden("Admin role required")

    instance = None
    if id:
        instance = get_object_or_404(AdminQPR, pk=id)
    if request.method == 'GET':
        forbidden_qpr_params = {
            'csrfmiddlewaretoken', 'form_type', 'quarter', 'financial_year', 
            'a_s2_meetings_count', 'a_s2_hindi_minutes', 'a_s3_total_documents',
            'a_s4_total_letters', 'a_s5_region_a_english_letters', 'role_form'
        }
        if any(param in request.GET for param in forbidden_qpr_params):
            return HttpResponseBadRequest("Bad Request: Form parameters are not allowed in the query string.")
    if request.method == 'POST':
        querystring_error = reject_querystring_on_post(request)
        if querystring_error:
            return querystring_error

        if instance:
            form = AdminQPRForm(request.POST, instance=instance)
        else:
            form = AdminQPRForm(request.POST)

        if form.is_valid():
            quarter = form.cleaned_data.get('quarter')
            financial_year = form.cleaned_data.get('financial_year')
            if not instance and AdminQPR.objects.filter(user=request.user, quarter=quarter, financial_year=financial_year).exists():
                messages.error(request, "Admin QPR for this quarter and financial year has already been filled.")
            else:
                obj = form.save(commit=False)
                obj.user = request.user
                obj.is_submitted = True
                obj.submitted_at = timezone.now()
                obj.save()
                messages.success(request, "Admin QPR saved successfully.")
                return redirect('admin_qpr_detail', id=obj.id)
    else:
        if instance:
            form = AdminQPRForm(instance=instance)
        else:
            form = AdminQPRForm()

    return render(request, 'qpr/admin_qpr_form.html', {'form': form, 'instance': instance})


@login_required
def admin_qpr_detail(request, id):
    obj = get_object_or_404(AdminQPR, id=id)
    if obj.user != request.user and not (request.user.is_staff or user_has_role(request.user, 'admin')):
        return HttpResponseForbidden()

    form = AdminQPRForm(instance=obj)
    for name in form.fields:
        try:
            form.fields[name].widget.attrs['disabled'] = 'disabled'
        except Exception:
            pass

    return render(request, 'qpr/admin_qpr_form.html', {'form': form, 'instance': obj, 'readonly': True})

@login_required
def qpr_hod_dashboard(request):
    """HOD Dashboard - Department overview and employee statistics"""

    if not user_has_role(request.user, 'hod'):
        return redirect('/')

    lang = request.session.get('lang', 'en')
    profile_change_requests = ProfileChangeRequest.objects.filter(
        hod=request.user,
        status='pending'
    ).select_related('profile', 'profile__user').order_by('-requested_at')

    current_quarter = get_current_quarter()
    current_year = get_current_year_label()

    hod_profile = UserProfile.objects.select_related('user').get(user=request.user)
    hod_name = (hod_profile.hod_name or hod_profile.name or "").strip()


    if hod_name:
        user_role_q = Q(roles__name='user') | Q(user__roles__name='user')

        users_under_hod = UserProfile.objects.filter(
            ((user_role_q & Q(hod_name__iexact=hod_name)) |
            Q(user=request.user)) & Q(approval_status__iexact='approved')
        ).distinct()
    else:
        users_under_hod = UserProfile.objects.filter(user=request.user, approval_status__iexact='approved').distinct()

    total_users = users_under_hod.count()
    qpr_submitted_count = 0

    today = timezone.localdate()
    for up in users_under_hod:
        try:
            submitted_today = up.user.qpr_records.filter(
                frequency__iexact='daily',
                period_start=today,
                is_submitted=True
            ).exists()
            if submitted_today:
                qpr_submitted_count += 1
        except Exception:
            continue

    qpr_pending = total_users - qpr_submitted_count
    profile_updated_count = users_under_hod.filter(profile_updated=True).count()

    pending_approvals = UserProfile.objects.filter(
            approval_status='pending'
        ).filter(
            Q(hod_name__iexact=hod_name) |
            Q(hod_name__iexact=hod_profile.employee_code) |
            Q(hod_name=str(hod_profile.employee_code))
        ).select_related('user', 'employee')
    context = {
        'role': 'hod',
        'total_users': total_users,
        'qpr_submitted': qpr_submitted_count,
        'qpr_pending': qpr_pending,
        'profile_updated': profile_updated_count,
        'hod_name': hod_name,

        'profile_change_requests': profile_change_requests,

        'current_lang': lang,
        'current_quarter': current_quarter,
        'current_year': current_year,
        'pending_approvals': pending_approvals,
    }

    response = render(request, 'qpr/hod_dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    logger.debug("HOD name: %s", hod_name)
    logger.debug("HOD empcode: %s", hod_profile.employee_code if hod_profile else None)
    logger.debug("Pending count: %s", pending_approvals.count())


    return response

@login_required
def manager_dashboard(request):
    """Manager Dashboard - Manage system access and employee records"""
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    manager_office = getattr(request.user.profile, 'office_code', None)

    users = CustomUser.objects.select_related('profile').filter(
        profile__office_code=manager_office,
        profile__approval_status='approved',
    ).order_by('-date_joined')

    user_search = (request.GET.get('user_q') or '').strip()
    hindi_exam_filter = (request.GET.get('hindi_exam') or '').strip()

    office_employee_codes_qs = CustomUser.objects.filter(
        profile__office_code=manager_office,
        profile__approval_status='approved',
    ).values_list('profile__employee_code', flat=True)
    office_employee_codes = []
    for code in office_employee_codes_qs:
        if code is None:
            continue
        try:
            office_employee_codes.append(int(str(code).strip()))
        except (ValueError, TypeError):
            continue

    if office_employee_codes:
        raw_employees = Employee.objects.filter(empcode__in=office_employee_codes).order_by('-lastupdate')
    else:
        raw_employees = Employee.objects.none()

    employee_by_code = {str(emp.empcode): emp for emp in raw_employees}

    employee_data = []

    for emp in raw_employees:
        user = CustomUser.objects.filter(profile__employee_code=emp.empcode).first()

        qpr_status_text = "Not Started"
        qpr_is_submitted = False
        latest_qpr_id = None
        qpr_last_updated = None

        linked_user_id = getattr(user, 'id', None) if user else None

        if user:
            latest_qpr = QPRRecord.objects.filter(user=user).order_by('-updated_at').first()
            if latest_qpr:
                qpr_is_submitted = latest_qpr.is_submitted
                qpr_status_text = "Submitted" if qpr_is_submitted else "Draft"
                latest_qpr_id = getattr(latest_qpr, 'id', None)
                qpr_last_updated = latest_qpr.updated_at

        employee_data.append({
            'empcode': emp.empcode,
            'name': emp.ename,
            'designation': emp.designation,
            'hname': emp.hname,
            'user_id': linked_user_id,
            'status': emp.status,
            'lastupdate': emp.lastupdate,
            'qpr_status': qpr_status_text,
            'qpr_is_submitted': qpr_is_submitted,
            'qpr_id': latest_qpr_id,
            'qpr_last_updated': qpr_last_updated
        })

    application_users = []
    for app_user in users:
        profile = getattr(app_user, 'profile', None)
        employee_code = str(getattr(profile, 'employee_code', '') or '').strip()
        employee = employee_by_code.get(employee_code) or getattr(profile, 'employee', None)
        employee_name = (
            getattr(employee, 'ename', None)
            or getattr(profile, 'name', None)
            or app_user.get_full_name()
            or app_user.username
        )
        highest_exam = getattr(employee, 'highest_exam', '') or ''

        if user_search:
            search_target = ' '.join([
                app_user.username or '',
                employee_code,
                employee_name or '',
                getattr(employee, 'hname', '') or '',
            ]).lower()
            if user_search.lower() not in search_target:
                continue

        if hindi_exam_filter and hindi_exam_filter not in highest_exam:
            continue

        application_users.append({
            'user': app_user,
            'empcode': employee_code or app_user.username,
            'employee_name': employee_name,
            'status': 'Active' if app_user.is_active else 'Inactive',
            'is_active': app_user.is_active,
            'highest_exam': highest_exam,
        })

    highest_exam_options = [
        'Prabodh',
        'Praveen',
        'Pragya',
        'Parangat',
    ]

    pending_profile_requests = ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='pending')

    manager_office = getattr(request.user.profile, 'office_code', None)
    pending_qpr_edits = []
    edit_requests_by_user = {}

    if manager_office:
        edit_requests = EditRequest.objects.filter(
            request_type='qpr',
            status__in=['pending', 'approved']  
        ).select_related('user').filter(
            user__profile__office_code=manager_office
        )

        pending_qpr_edits = [req for req in edit_requests if req.status == 'pending']

        for req in edit_requests:
            if req.user_id not in edit_requests_by_user or req.created_at > edit_requests_by_user[req.user_id].created_at:
                edit_requests_by_user[req.user_id] = req

    for emp in employee_data:
        emp['pending_edit_request'] = None
        emp['approved_edit_request'] = None

        if emp['user_id'] in edit_requests_by_user:
            req = edit_requests_by_user[emp['user_id']]
            if req.status == 'pending':
                emp['pending_edit_request'] = req
            elif req.status == 'approved':
                emp['approved_edit_request'] = req

    context = {
        'users': users,
        'application_users': application_users,
        'user_search': user_search,
        'hindi_exam_filter': hindi_exam_filter,
        'highest_exam_options': highest_exam_options,
        'employees': employee_data,
        'pending_profile_requests': pending_profile_requests,
        'pending_qpr_edits': pending_qpr_edits,
    }
    return render(request, 'manager_dashboard.html', context)



def _can_manage_employee_master(user):
    return user.is_authenticated and (
        user_has_role(user, ['manager', 'admin']) or user.is_superuser
    )


@login_required
def manager_employee_master_list(request):
    if not _can_manage_employee_master(request.user):
        return redirect('/')

    query = (request.GET.get('q') or '').strip()
    designation = (request.GET.get('designation') or '').strip()
    state = (request.GET.get('state') or '').strip()
    status_filter = (request.GET.get('status') or 'active').strip().lower()

    employees = EmployeeMaster.objects.all().order_by('empcode')

    if query:
        query_filter = (
            Q(name__icontains=query) |
            Q(hindi_name__icontains=query) |
            Q(division__icontains=query)
        )
        if query.isdigit():
            query_filter |= Q(empcode=int(query))
        employees = employees.filter(query_filter)

    if designation:
        employees = employees.filter(designation__iexact=designation)

    if state:
        employees = employees.filter(state__iexact=state)

    if status_filter == 'active':
        employees = employees.filter(is_active=True)
    elif status_filter == 'inactive':
        employees = employees.filter(is_active=False)

    paginator = Paginator(employees, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'selected_designation': designation,
        'selected_state': state,
        'selected_status': status_filter,
        'designation_options': EmployeeMaster.objects.exclude(
            designation__isnull=True
        ).exclude(
            designation__exact=''
        ).values_list('designation', flat=True).distinct().order_by('designation'),
        'state_options': EmployeeMaster.objects.exclude(
            state__isnull=True
        ).exclude(
            state__exact=''
        ).values_list('state', flat=True).distinct().order_by('state'),
    }
    return render(request, 'manager_employee_master_list.html', context)


@login_required
def manager_employee_master_add(request):
    if not _can_manage_employee_master(request.user):
        return redirect('/')

    if request.method == 'GET':
        form_indicators = ['empcode', 'name', 'mobile', 'designation', 'state']
        if any(param in request.GET for param in form_indicators):
            return HttpResponseBadRequest("Bad Request: Form data parameters cannot be accepted via query string link.")    

    if request.method == 'POST':
        querystring_error = reject_querystring_on_post(request)
        if querystring_error:
            return querystring_error

        form = EmployeeMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Employee added to master table successfully.")
            return redirect('manager_employee_master_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = EmployeeMasterForm(initial={'is_active': True})

    return render(request, 'manager_employee_master_form.html', {
        'form': form,
        'page_title': 'Add Master Employee',
        'submit_label': 'Add Employee',
        'is_edit': False,
    })


@login_required
def manager_employee_master_edit(request, employee_id):
    if not _can_manage_employee_master(request.user):
        return redirect('/')

    if request.method == 'GET':
        form_indicators = ['empcode', 'name', 'mobile', 'designation', 'state']
        if any(param in request.GET for param in form_indicators):
            return HttpResponseBadRequest("Bad Request: Form data parameters cannot be accepted via query string link.")

    employee = get_object_or_404(EmployeeMaster, id=employee_id)

    if request.method == 'POST':
        form = EmployeeMasterForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f"Employee {employee.empcode} updated successfully.")
            return redirect('manager_employee_master_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = EmployeeMasterForm(instance=employee)

    return render(request, 'manager_employee_master_form.html', {
        'form': form,
        'employee_master': employee,
        'page_title': 'Edit Master Employee',
        'submit_label': 'Save Changes',
        'is_edit': True,
    })


@login_required
@require_http_methods(["POST"])
def manager_employee_master_toggle_status(request, employee_id):
    if not _can_manage_employee_master(request.user):
        return redirect('/')

    employee = get_object_or_404(EmployeeMaster, id=employee_id)
    action = (request.POST.get('action') or '').strip().lower()
    remarks = (request.POST.get('remarks') or '').strip()

    if action == 'deactivate':
        employee.is_active = False
        employee.transferred_at = timezone.localdate()
        if remarks:
            employee.remarks = remarks
        employee.save(update_fields=['is_active', 'transferred_at', 'remarks', 'updated_at'])
        messages.success(request, f"Employee {employee.empcode} marked as transferred out.")
    elif action == 'activate':
        employee.is_active = True
        employee.transferred_at = None
        if remarks:
            employee.remarks = remarks
            employee.save(update_fields=['is_active', 'transferred_at', 'remarks', 'updated_at'])
        else:
            employee.save(update_fields=['is_active', 'transferred_at', 'updated_at'])
        messages.success(request, f"Employee {employee.empcode} reactivated successfully.")
    else:
        messages.error(request, "Invalid employee master action.")

    return redirect('manager_employee_master_list')


@login_required
@require_http_methods(["POST"])
def manager_employee_master_delete(request, employee_id):
    if not _can_manage_employee_master(request.user):
        return redirect('/')

    employee = get_object_or_404(EmployeeMaster, id=employee_id)
    empcode = employee.empcode
    employee.delete()
    messages.success(request, f"Employee {empcode} deleted permanently from the master table.")
    return redirect('manager_employee_master_list')

@login_required
def admin_dashboard(request):
    if user_role(request.user) != 'admin': return redirect('/')
    admin_state = request.user.profile.office_state
    if not admin_state:
        messages.warning(request, "Mandatory: You must set your Office State in your profile before accessing the Admin Dashboard.")
        return redirect('profile')
   
    users = CustomUser.objects.filter(is_active=True, is_archived=False, profile__office_state=admin_state).order_by('-date_joined')
   
    archived_users = ArchivedUser.objects.all().order_by('-archived_at')

    today = timezone.localdate()
   
    hod_stats = []
    hods = UserProfile.objects.filter(
        Q(roles__name='hod') | Q(user__roles__name='hod'),
        office_state=admin_state
    ).select_related('user', 'employee').distinct().order_by('name')
    for hod_profile in hods:
        employee_master = None
        try:
            if hod_profile.employee_code:
                employee_master = EmployeeMaster.objects.filter(
                    empcode=int(hod_profile.employee_code)
                ).first()
        except (TypeError, ValueError):
            employee_master = None
        hod_identifiers = [
            (hod_profile.employee_code or '').strip(),
            (hod_profile.name or '').strip(),
            (hod_profile.hod_name or '').strip(),
            (getattr(hod_profile.user, 'username', '') or '').strip(),
        ]
        hod_identifiers = [value for value in hod_identifiers if value]
        hod_display = (
            (hod_profile.name or '').strip()
            or (getattr(employee_master, 'name', '') or '').strip()
            or (getattr(hod_profile.employee, 'ename', '') or '').strip()
            or (hod_profile.user.get_full_name() or '').strip()
            or (getattr(hod_profile.user, 'username', '') or '').strip()
            or (hod_profile.employee_code or '').strip()
            or 'UNKNOWN'
        )
        hod_ip_number = (
            (hod_profile.ip_number or '').strip()
            or (getattr(employee_master, 'ip_number', '') or '').strip()
            or '-'
        )
        hod_filter = Q()
        for identifier in hod_identifiers:
            hod_filter |= Q(hod_name__iexact=identifier)
        if hod_identifiers:
            users_under_hod = UserProfile.objects.filter(
                hod_filter,
                approval_status__iexact='approved',
                office_state=admin_state
            ).filter(
                Q(roles__name='user') | Q(user__roles__name='user')
            ).distinct()
        else:
            users_under_hod = UserProfile.objects.none()
        total_users = users_under_hod.count()
        profile_complete = sum(1 for p in users_under_hod if p.profile_updated)
        qpr_complete = sum(
            1 for p in users_under_hod if QPRRecord.objects.filter(
                user=p.user,
                frequency__iexact='daily',
                period_start=today,
                is_submitted=True
            ).exists()
        )
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        hod_stats.append({
            'employee_code': hod_profile.employee_code or '-',
            'hod_name': str(hod_display).upper(),
            'ip_number': hod_ip_number,
            'total_employees': total_users,
            'profile_completed': profile_complete,
            'qpr_completed': qpr_complete,
            'completion_percentage': completion_pct,
        })
    unique_hod_names = set(UserProfile.objects.filter(
        Q(roles__name='user') | Q(user__roles__name='user'),
        approval_status__iexact='approved',
        office_state=admin_state
    ).exclude(hod_name__isnull=True).exclude(hod_name__iexact='ADMIN').values_list('hod_name', flat=True))
    actual_hod_profiles = UserProfile.objects.filter(
        Q(roles__name='hod') | Q(user__roles__name='hod'),
        office_state=admin_state
    ).select_related('user').distinct()
    actual_hod_names = set()
    for hod_profile in actual_hod_profiles:
        actual_hod_names.update(
            value for value in [
                hod_profile.employee_code,
                hod_profile.name,
                hod_profile.hod_name,
                getattr(hod_profile.user, 'username', None),
            ] if value
        )
    uncovered = unique_hod_names - actual_hod_names
    for hod_name in sorted(uncovered):
        users_under_hod = UserProfile.objects.filter(
            Q(roles__name='user') | Q(user__roles__name='user'),
            hod_name__iexact=hod_name,
            approval_status__iexact='approved',
            office_state=admin_state
        ).distinct()
        total_users = users_under_hod.count()
        qpr_complete = sum(
            1 for p in users_under_hod if QPRRecord.objects.filter(
                user=p.user,
                frequency__iexact='daily',
                period_start=today,
                is_submitted=True
            ).exists()
        )
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        hod_stats.append({
            'employee_code': '-',
            'hod_name': str(hod_name).upper(),
            'ip_number': '-',
            'total_employees': total_users,
            'profile_completed': sum(1 for p in users_under_hod if p.profile_updated),
            'qpr_completed': qpr_complete,
            'completion_percentage': completion_pct,
        })
    pending_requests = ManagerRequest.objects.filter(status='pending', hod__roles__name='user', hod__profile__office_state=admin_state)
    pending_admin_approvals = UserProfile.objects.filter(
            approval_status='pending_admin',
            hod_name__iexact='ADMIN',
            office_state=admin_state,
        ).select_related('user', 'employee').order_by('-created_at')
    context = {
        'role': 'admin',
        'hod_stats': hod_stats,
        'manager_requests': pending_requests,
        'pending_admin_approvals': pending_admin_approvals,
        'users': users,
        'archived_users': archived_users
    }
    response = render(request, 'dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
def admin_create_hod(request):
    if not user_has_role(request.user, 'admin'): return redirect('/')
    admin_state = request.user.profile.office_state
    found_name = ''
    if request.method == 'GET':
        forbidden_hod_params = {'csrfmiddlewaretoken', 'emp_code'}
        if any(param in request.GET for param in forbidden_hod_params):
            return HttpResponseBadRequest("Bad Request: Form parameters are not allowed in the query string.")
    if request.method == 'POST':
        querystring_error = reject_querystring_on_post(request)
        if querystring_error:
            return querystring_error

        emp_code = request.POST.get('emp_code', '').strip()
        if not emp_code:
            messages.error(request, 'Employee code is required')
        else:
            try:
                profile = UserProfile.objects.get(employee_code=emp_code, office_state=admin_state)
                display_name = profile.name or profile.user.get_full_name() or profile.user.username
                found_name = display_name
                if profile.roles.filter(name='hod').exists():
                    messages.error(request, 'This user is already assigned a HOD role')
                else:
                    hod_role = Role.objects.get(name='hod')
                    user_role_obj = Role.objects.get(name='user')
                    profile.roles.add(hod_role, user_role_obj)
                    profile.approval_status = 'approved'
                    try:
                        profile.user.roles.add(hod_role, user_role_obj)
                        profile.user.save()
                    except Exception:
                        pass
                    profile.hod_name = emp_code
                    profile.profile_updated = True
                    profile.save()
                    messages.success(request, f'HOD {display_name} created!')
                    return redirect('qpr_admin_dashboard')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User has not registered or entered employee code is incorrect')
    return render(request, 'qpr/admin_create_hod.html', {'found_name': found_name})

@login_required
def admin_create_manager(request):
    if not user_has_role(request.user, 'admin'): return redirect('/')
    admin_state = request.user.profile.office_state
    found_name = ''
    if request.method == 'GET':
        forbidden_hod_params = {'csrfmiddlewaretoken', 'emp_code'}
        if any(param in request.GET for param in forbidden_hod_params):
            return HttpResponseBadRequest("Bad Request: Form parameters are not allowed in the query string.")
    if request.method == 'POST':
        emp_code = request.POST.get('emp_code', '').strip()
        if not emp_code:
            messages.error(request, 'Employee code is required')
        else:
            try:
                profile = UserProfile.objects.get(employee_code=emp_code, office_state=admin_state)
                display_name = profile.name or profile.user.get_full_name() or profile.user.username
                found_name = display_name
                if profile.roles.filter(name='manager').exists():
                    messages.error(request, 'This user is already assigned a Manager role')
                else:
                    manager_role = Role.objects.get(name='manager')
                    user_role_obj = Role.objects.get(name='user')
                    profile.roles.add(manager_role, user_role_obj)
                    profile.approval_status = 'approved'
                    try:
                        profile.user.roles.add(manager_role, user_role_obj)
                        profile.user.save()
                    except Exception:
                        pass
                    profile.profile_updated = True
                    profile.save()
                    messages.success(request, f'Manager {display_name} created!')
                    return redirect('qpr_admin_dashboard')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User has not registered or entered employee code is incorrect')
    return render(request, 'qpr/admin_create_manager.html', {'found_name': found_name})


def admin_api_get_employee_details(request):
    admin_state = request.user.profile.office_state
    emp_code = request.GET.get('emp_code', '').strip()
   
    if not emp_code:
        return JsonResponse({'error': 'Employee code is required'}, status=400)
   
    try:
        profile = UserProfile.objects.get(employee_code=emp_code, office_state=admin_state)
        roles = list(profile.roles.values_list('name', flat=True))
        display_name = profile.name or profile.user.get_full_name() or profile.user.username
        return JsonResponse({
            'success': True,
            'name': display_name,
            'employee_code': profile.employee_code,
            'roles': roles or ['user']
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({
            'error': 'User has not registered or entered employee code is incorrect'
        }, status=404)

@login_required
@require_POST
def api_create_office(request):
    querystring_error = reject_querystring_on_post(request)
    if querystring_error:
        return querystring_error

    if not user_has_role(request.user, 'admin'):
        messages.error(request, 'Permission denied')
        return redirect('qpr_admin_dashboard')
   
    admin_state = getattr(request.user.profile, 'office_state', '').strip()
    if not admin_state:
        messages.error(request, "Your profile is missing a state. Please update your profile first.")
        return redirect('profile')

    code = request.POST.get('office_code', '').strip()
    name = request.POST.get('office_name', '').strip()
    if not code or not name:
        messages.error(request, 'Office code and name are required')
        return redirect('qpr_admin_dashboard')

    office, created = Office.objects.get_or_create(
        code=code,
        defaults={'name': name,'state': admin_state}
    )
    if not created:
        messages.error(request, 'Office code already exists')
        return redirect('qpr_admin_dashboard')

    messages.success(request, f'Office {office.code} - {office.name} created for {admin_state}')
    return redirect('qpr_admin_dashboard')


def api_list_offices(request):
    """Return list of offices for dropdowns"""
    offices = list(Office.objects.all().values('code', 'name'))
    return JsonResponse({'offices': offices})

@login_required
def admin_approve_request(request, request_id):
    if not user_has_role(request.user, 'admin'): return redirect('/')
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
    if not user_has_role(request.user, 'admin'): return redirect('/')
    admin_state = request.user.profile.office_state
    employee_code_filter = request.GET.get('employee_code', '').strip()
    name_filter = request.GET.get('name', '').strip()

    hods = UserProfile.objects.filter(
        Q(roles__name='hod') | Q(user__roles__name='hod'),
        office_state=admin_state
    ).select_related('user').distinct().order_by('name')
    hod_groups = []
   
    for hod_profile in hods:
        hod_employee_master = None
        try:
            if hod_profile.employee_code:
                hod_employee_master = EmployeeMaster.objects.filter(
                    empcode=int(hod_profile.employee_code)
                ).first()
        except (TypeError, ValueError):
            hod_employee_master = None

        hod_display_name = (
            (hod_profile.name or '').strip()
            or (getattr(hod_employee_master, 'name', '') or '').strip()
            or (hod_profile.user.get_full_name() or '').strip()
            or (getattr(hod_profile.user, 'username', '') or '').strip()
            or (hod_profile.employee_code or '').strip()
            or 'UNKNOWN'
        )
        hod_identifiers = [
            (hod_profile.employee_code or '').strip(),
            (hod_profile.name or '').strip(),
            (hod_profile.hod_name or '').strip(),
            (getattr(hod_profile.user, 'username', '') or '').strip(),
        ]
        hod_filter = Q()
        for identifier in [value for value in hod_identifiers if value]:
            hod_filter |= Q(hod_name__iexact=identifier)

        if hod_filter:
            users_under_hod = UserProfile.objects.filter(
                hod_filter,
                office_state=admin_state
            ).filter(
                Q(roles__name='user') | Q(user__roles__name='user')
            ).select_related('user', 'employee').distinct().order_by('name')
        else:
            users_under_hod = UserProfile.objects.none()

        user_details = []
        for user_profile in users_under_hod:
            emp_code_val = (user_profile.employee_code or '').strip()
            if employee_code_filter and employee_code_filter.lower() not in emp_code_val.lower():
                continue

            employee_master = None
            emp_record = None
            if emp_code_val:
                try:
                    employee_master = EmployeeMaster.objects.filter(empcode=int(emp_code_val)).first()
                    emp_record = user_profile.employee or Employee.objects.filter(empcode=int(emp_code_val)).first()
                except (TypeError, ValueError):
                    employee_master = None
                    emp_record = user_profile.employee
            if not emp_record:
                emp_record = user_profile.employee

            user_name = (
                (user_profile.name or '').strip()
                or (getattr(employee_master, 'name', '') or '').strip()
                or (getattr(emp_record, 'ename', '') or '').strip()
                or (user_profile.user.get_full_name() or '').strip()
                or (user_profile.user.username or '').strip()
            )
            hindi_name = (
                (getattr(employee_master, 'hindi_name', '') or '').strip()
                or (getattr(emp_record, 'hname', '') or '').strip()
                or ''
            )
            ip_number = (
                (user_profile.ip_number or '').strip()
                or (getattr(employee_master, 'ip_number', '') or '').strip()
                or '-'
            )

            if name_filter and name_filter.lower() not in (user_name or '').lower():
                continue

            office_name_val = user_profile.office_name or getattr(employee_master, 'division', '') or ''
            office_code_val = user_profile.office_code or ''

            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_name,
                'hname': hindi_name or 'Not Set',
                'ip_number': ip_number,
                'office_name': office_name_val or 'Not Set',
                'office_code': office_code_val or 'Not Set',
            })
        if user_details:
            hod_groups.append({
                'hod_name': hod_display_name,
                'hod_email': hod_profile.user.email,
                'hod_emp_code': hod_profile.employee_code,
                'user_count': len(user_details),
                'users': user_details
            })
   
    context = {
        'hod_groups': hod_groups,
        'employee_code_filter': employee_code_filter,
        'name_filter': name_filter,
    }
    return render(request, 'qpr/admin_employee_list.html', context)

@user_passes_test(lambda u: user_has_role(u, ['hod', 'admin']))
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

@user_passes_test(lambda u: u.is_authenticated and (user_has_role(u, ['hod', 'admin']) or u.is_superuser))
def manage_user_action(request, user_id, action):
    if action == 'unlock_qpr':
        if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
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

    try:
        target_user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        profile = get_object_or_404(UserProfile, employee_code=user_id)
        target_user = profile.user

    lang = request.session.get('lang', 'en')
   
    if action in ['archive', 'unarchive']:
        if not (user_has_role(request.user, ['admin']) or request.user.is_superuser):
            messages.error(request, translate_text("Only Admins can perform this action.", lang))
            return redirect('manager_dashboard')
        if not request.user.is_superuser:
            admin_state = request.user.profile.office_state
            target_state = getattr(target_user.profile, 'office_state', None)
            if admin_state != target_state:
                messages.error(request, translate_text("You can only manage users within your own state.", lang))
                return redirect('dashboard')
       
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

    elif action == 'unlock_record':
        emp = Employee.objects.filter( empcode=int(target_user.profile.employee_code)).first()
        if emp:
            emp.status = 'draft'
            emp.save()
            target_user.is_edit_allowed = True
            target_user.save()
            messages.success(request, "Record unlocked.")
    return redirect('manager_dashboard')

@login_required
def qpr_form(request):
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.approval_status != 'approved':
        messages.error(request, "Access Denied: Your account must be approved by your HOD before you can submit a QPR.")
        return redirect('dashboard')
   
    ensure_current_financial_year()
   
    profile_office_name = profile.office_name if profile and profile.office_name else ''
    profile_office_code = profile.office_code if profile and profile.office_code else ''
    profile_phone = profile.phone if profile and profile.phone else ''
    profile_email = profile.email if profile and profile.email else (request.user.get_email() if hasattr(request.user, 'get_email') else '')

    used = []
    for r in QPRRecord.objects.filter(user=request.user):
        used.append({'quarter': r.quarter, 'year': r.year or '', 'record_id': r.pk})

   

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
    qpr_popup_error = request.session.pop('qpr_popup_error', '')
    if qpr_popup_error:
        context['qpr_popup_error'] = qpr_popup_error

    today = timezone.localdate()
    month = today.month
   
    if 4 <= month <= 6:
        current_quarter = '30 जून / Jun 30'
    elif 7 <= month <= 9:
        current_quarter = '30 सितंबर / Sep 30'
    elif 10 <= month <= 12:
        current_quarter = '31 दिसंबर / Dec 31'
    else:
        current_quarter = '31 मार्च / Mar 31'

    fiscal_year_start = today.year - 1 if month < 4 else today.year
    current_financial_year = f"{fiscal_year_start}-{fiscal_year_start + 1}"
    min_start = 2024
    financial_years = []
    for s in range(min_start, fiscal_year_start + 1):
        financial_years.append({'start_year': s, 'end_year': s + 1})

    context.update({
        'current_quarter': current_quarter,
        'current_year': current_financial_year,
        'financial_years': financial_years,
        'user_role': getattr(request.user, 'role', None),
        'active_role': request.session.get('active_role', getattr(request.user, 'role', None)),
        'has_hod_role': user_has_role(request.user, 'hod'),
        'server_month': today.month,
        'server_year': today.year,
        'profile_language_region': profile.language_region if profile else '',
    })
    try:
        records_qs = QPRRecord.objects.filter(user=request.user).order_by('-id')
        records = []
        requested_edit_record_id = (request.GET.get('edit_record') or '').strip()
        requested_edit_scope = (request.GET.get('edit_scope') or '').strip().lower()
        for r in records_qs:
            d = serialize_qpr_record(r)
            approved_request = _add_qpr_edit_flags(d, r, request.user, request.user)
            if (
                requested_edit_scope in SNAPSHOT_EDIT_SCOPES
                and requested_edit_record_id
                and str(r.pk) == requested_edit_record_id
            ):
                scoped_request = _approved_qpr_edit_request(request.user, r, requested_edit_scope)
                if scoped_request:
                    approved_request = scoped_request
                    d['edit_approved'] = True
                    d['edit_approved_scope'] = requested_edit_scope
                    d['can_edit'] = False
                    d['snapshot_can_edit'] = True
            if approved_request:
                requested_data = approved_request.requested_data or {}
                edit_scope = (requested_data.get('edit_scope') or '').lower()
                if edit_scope in SNAPSHOT_EDIT_SCOPES:
                    ps, pe = _snapshot_bounds_for_record(r, edit_scope)
                    snapshot = _snapshot_for_record(r, edit_scope)
                    details = None
                    if snapshot:
                        if not getattr(snapshot, 'is_overwritten', False):
                            if edit_scope == 'weekly':
                                snapshot, _ = _rebuild_weekly_snapshot_from_source(r.user, ps, pe, r.quarter, r.year)
                            elif edit_scope == 'monthly':
                                snapshot, _ = _rebuild_monthly_snapshot_from_source(r.user, ps, pe, r.quarter, r.year)
                            elif edit_scope == 'quarterly':
                                snapshot, _ = _rebuild_quarterly_snapshot_from_source(r.user, r.quarter, r.year)
                        details = _snapshot_details(snapshot)
                    if details is None and ps and pe:
                        details = _aggregate_records_with_fallback(r.user, ps, pe, preferred=edit_scope)
                    if details is not None:
                        d['snapshot_edit'] = {
                            'scope': edit_scope,
                            'period_start': ps.isoformat() if ps else '',
                            'period_end': pe.isoformat() if pe else '',
                            'details': details,
                        }
                        d.setdefault('cumulative', {})[edit_scope] = details
            records.append(d)
    except Exception:
        records = []
    import json as _json
    context['records_json'] = _json.dumps(records, default=str)

    try:
        selected_date = timezone.localdate()
        availability = _allowed_frequencies_for_date(request.user, selected_date, allow_future_days=False)
        context['availability_json'] = _json.dumps(availability, default=str)
        context['selected_date'] = selected_date.isoformat()
    except Exception:
        context['availability_json'] = None
        context['selected_date'] = timezone.localdate().isoformat()

    try:
        selected_date = timezone.localdate()
        context['missing_days_weekly'] = _get_missing_days_context(
            request.user, 'weekly', selected_date, current_quarter, current_financial_year
        )
        context['missing_days_monthly'] = _get_missing_days_context(
            request.user, 'monthly', selected_date, current_quarter, current_financial_year
        )
        context['missing_days_quarterly'] = _get_missing_days_context(
            request.user, 'quarterly', selected_date, current_quarter, current_financial_year
        )
        context['missing_days_json'] = _json.dumps({
            'weekly': context['missing_days_weekly'],
            'monthly': context['missing_days_monthly'],
            'quarterly': context['missing_days_quarterly']
        })
        context['missing_days_source_json'] = _json.dumps(_missing_days_client_source(request.user), default=str)
    except Exception:
        logger.exception("Failed to get missing days context")
        context['missing_days_weekly'] = {'missing_days': [], 'has_fill': False, 'fill_fields_count': 0, 'message': ''}
        context['missing_days_monthly'] = {'missing_days': [], 'has_fill': False, 'fill_fields_count': 0, 'message': ''}
        context['missing_days_quarterly'] = {'missing_days': [], 'has_fill': False, 'fill_fields_count': 0, 'message': ''}
        context['missing_days_json'] = _json.dumps({})
        context['missing_days_source_json'] = _json.dumps({'submitted_daily_dates': [], 'fills': {'weekly': [], 'monthly': [], 'quarterly': []}})

    return render(request, 'qpr/qpr_form.html', context)

@login_required
def report_list(request):
    emp_code = (request.GET.get('emp_code') or '').strip()
    target_user = request.user
    is_hod_view = False
    if emp_code:
        try:
            profile = UserProfile.objects.select_related('user').get(employee_code=emp_code)
        except UserProfile.DoesNotExist:
            messages.error(request, "Employee not found.")
            return redirect('qpr_hod_dashboard' if user_has_role(request.user, 'hod') else 'qpr_user_dashboard')

        target_user = profile.user
        is_hod_view = (getattr(target_user, 'id', None) != getattr(request.user, 'id', None))

        if is_hod_view:
            allowed = False
            if user_has_role(request.user, 'admin') or request.user.is_superuser:
                allowed = True

            if not allowed and user_has_role(request.user, 'hod'):
                allowed = True
                requester_hod = (getattr(request.user.profile, 'hod_name', None) or getattr(request.user.profile, 'name', None))
                target_hod = (getattr(target_user, 'profile', None) and (getattr(target_user.profile, 'hod_name', None) or getattr(target_user.profile, 'name', None)))
                if requester_hod and target_hod and str(requester_hod).strip().lower() != str(target_hod).strip().lower():
                    messages.error(request, "Unauthorized to view reports for this employee.")
                    return redirect('qpr_hod_dashboard')

            if not allowed and user_has_role(request.user, 'manager'):
                mgr_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
                mgr_office = getattr(mgr_profile, 'office_code', None)
                tgt_profile = getattr(target_user, 'profile', None)
                tgt_office = getattr(tgt_profile, 'office_code', None)
                if mgr_office and tgt_office and str(mgr_office).strip() == str(tgt_office).strip():
                    allowed = True

            if not allowed:
                messages.error(request, "Unauthorized to view other user's reports.")
                return redirect('home')

    context = {
        'target_user_id': getattr(target_user, 'id', ''),
        'is_hod_view': is_hod_view,
        'today_iso': timezone.localdate().isoformat(),
        'emp_code_filter': emp_code,
    }

    # Extract raw values then strictly remove structural HTML chars to prevent XSS
    raw_quarter = (request.GET.get('quarter') or '').strip() or get_current_quarter()
    raw_year = (request.GET.get('year') or '').strip() or get_current_year_label()

    # Strip only structural characters that can break out of HTML/JS contexts
    for ch in ('<', '>', '"', "'"):
        if ch in raw_quarter:
            raw_quarter = raw_quarter.replace(ch, '')
        if ch in raw_year:
            raw_year = raw_year.replace(ch, '')

    # Escape any remaining HTML before using in templates or queries
    quarter = escape(raw_quarter)
    year = escape(raw_year)
    try:
        q_start, q_end = _quarter_label_to_daterange(quarter, year)
    except Exception:
        quarter = get_current_quarter()
        year = get_current_year_label()
        q_start, q_end = _quarter_label_to_daterange(quarter, year)
    assert q_start is not None and q_end is not None

    quarter_options = [
        '30 जून / Jun 30',
        '30 सितंबर / Sep 30',
        '31 दिसंबर / Dec 31',
        '31 मार्च / Mar 31',
    ]
    raw_year_values = QPRRecord.objects.filter(user=target_user).values_list('year', flat=True)
    year_values = []
    seen_years = set()
    for raw_year in raw_year_values:
        normalized_year = str(raw_year or '').strip()
        if normalized_year and normalized_year not in seen_years:
            seen_years.add(normalized_year)
            year_values.append(normalized_year)
    for required_year in (year, get_current_year_label()):
        normalized_year = str(required_year or '').strip()
        if normalized_year and normalized_year not in seen_years:
            seen_years.add(normalized_year)
            year_values.append(normalized_year)
    year_options = sorted(year_values, reverse=True)

    context.update({
        'quarter_filter': quarter,
        'year_filter': year,
        'quarter_options': quarter_options,
        'year_options': year_options,
    })

    try:
        records_qs = QPRRecord.objects.filter(user=target_user).filter(
            Q(period_start__lte=q_end, period_end__gte=q_start) |
            Q(quarter=quarter, year=year)
        ).order_by('-id')
        records = []
        for r in records_qs:
            d = serialize_qpr_record(r)
            _add_qpr_edit_flags(d, r, request.user, target_user)
            records.append(d)
    except Exception:
        records = []
    context['records_data'] = records
    try:
        default_region = ''
        try:
            profile = getattr(target_user, 'profile', None)
            if profile and getattr(profile, 'language_region', None):
                default_region = profile.language_region
        except Exception:
            default_region = ''

        daily = []
        weekly = []
        monthly = []
        quarterly = None
       
        if q_start and q_end:
            all_daily_recs_full = list(QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='daily',
                period_start__range=[q_start, q_end]
            ))
           
            all_daily_recs = list(QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='daily',
                period_start__range=[q_start, q_end]
            ).values('period_start', 'region'))
           
            all_weekly_snaps = list(WeeklySnapshot.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year,
                period_start__gte=q_start - timedelta(days=7),
                period_end__lte=q_end + timedelta(days=7)
            ))
           
            all_weekly_fills = list(WeeklyFill.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year,
                period_start__gte=q_start - timedelta(days=7),
                period_end__lte=q_end + timedelta(days=7)
            ))

            all_monthly_fills = list(MonthlyFill.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year,
                period_start__lte=q_end,
                period_end__gte=q_start
            ))
            all_quarterly_fills = list(QuarterlyFill.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year
            ))
           
            all_monthly_snaps = list(MonthlySnapshot.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year,
                period_start__gte=q_start - timedelta(days=31),
                period_end__lte=q_end + timedelta(days=31)
            ))
           
            quarterly_snap = QuarterlySnapshot.objects.filter(
                user=target_user,
                quarter=quarter,
                year=year
            ).first()
           
            all_daily_records = QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='daily',
                period_start__range=[q_start, q_end]
            )
            all_weekly_records = QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='weekly',
                period_start__lte=q_end,
                period_end__gte=q_start
            )
            all_monthly_records = QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='monthly',
                period_start__lte=q_end,
                period_end__gte=q_start
            )
            all_quarterly_records = QPRRecord.objects.filter(
                user=target_user,
                is_submitted=True,
                frequency__iexact='quarterly',
                period_start__lte=q_end,
                period_end__gte=q_start
            )
                       
            daily_by_date_full = {}
            for rec in all_daily_recs_full:
                daily_by_date_full[rec.period_start] = rec
           
            daily_by_date = {}
            for rec in all_daily_recs:
                daily_by_date[rec['period_start']] = rec
           
            weekly_by_range = {}
            for snap in all_weekly_snaps:
                weekly_by_range[(snap.period_start, snap.period_end)] = snap
           
            weekly_fill_by_range = {}
            for fill in all_weekly_fills:
                weekly_fill_by_range[(fill.period_start, fill.period_end)] = fill

            monthly_fill_by_range = {}
            for fill in all_monthly_fills:
                monthly_fill_by_range[(fill.period_start, fill.period_end)] = fill

            quarterly_fill = all_quarterly_fills[0] if all_quarterly_fills else None

            monthly_by_range = {}
            for snap in all_monthly_snaps:
                monthly_by_range[(snap.period_start, snap.period_end)] = snap

            weekly_ranges = [
                (r.period_start, r.period_end)
                for r in all_weekly_records
                if r.period_start is not None and r.period_end is not None
            ]
            weekly_record_by_range = {
                (r.period_start, r.period_end): r
                for r in all_weekly_records
                if r.period_start is not None and r.period_end is not None
            }
            monthly_ranges = [
                (r.period_start, r.period_end)
                for r in all_monthly_records
                if r.period_start is not None and r.period_end is not None
            ]
            quarterly_ranges = [
                (r.period_start, r.period_end)
                for r in all_quarterly_records
                if r.period_start is not None and r.period_end is not None
            ]
            first_weekly_fill_day_by_id = {}
            for (w_start, w_end), weekly_fill in weekly_fill_by_range.items():
                fill_id = getattr(weekly_fill, 'id', None)
                cur_fill_day = max(w_start, q_start)
                fill_end = min(w_end, q_end)
                while cur_fill_day <= fill_end:
                    if cur_fill_day.weekday() <= 5 and cur_fill_day not in daily_by_date_full:
                        first_weekly_fill_day_by_id[fill_id] = cur_fill_day
                        break
                    cur_fill_day = cur_fill_day + timedelta(days=1)

            def is_weekly_fill_day(day):
                return any(w_start <= day <= w_end for (w_start, w_end) in weekly_fill_by_range.keys())

            def is_monthly_fill_day(day):
                return any(m_start <= day <= m_end for (m_start, m_end) in monthly_fill_by_range.keys())

            first_monthly_fill_day_by_id = {}
            for (m_start, m_end), monthly_fill in monthly_fill_by_range.items():
                fill_id = getattr(monthly_fill, 'id', None)
                cur_fill_day = max(m_start, q_start)
                fill_end = min(m_end, q_end)
                while cur_fill_day <= fill_end:
                    if (
                        cur_fill_day.weekday() <= 5
                        and cur_fill_day not in daily_by_date_full
                        and not is_weekly_fill_day(cur_fill_day)
                    ):
                        first_monthly_fill_day_by_id[fill_id] = cur_fill_day
                        break
                    cur_fill_day = cur_fill_day + timedelta(days=1)

            first_quarterly_fill_day = None
            if quarterly_fill:
                cur_fill_day = q_start
                while cur_fill_day <= q_end:
                    if (
                        cur_fill_day.weekday() <= 5
                        and cur_fill_day not in daily_by_date_full
                        and not is_weekly_fill_day(cur_fill_day)
                        and not is_monthly_fill_day(cur_fill_day)
                    ):
                        first_quarterly_fill_day = cur_fill_day
                        break
                    cur_fill_day = cur_fill_day + timedelta(days=1)
           
            cur = q_start
            daily_debug = []
            while cur <= q_end:
                if cur.weekday() <= 5:
                    totals = {k: 0 for k in NUMERIC_KEYS}
                    filled_by_weekly = False
                    filled_by_monthly = False
                    filled_by_quarterly = False
                    is_first_fill_day = False
                    is_first_monthly_fill_day = False
                    is_first_quarterly_fill_day = False
                    weekly_fill_record_id = None
                    monthly_fill_record_id = None
                    quarterly_fill_record_id = None
                    weekly_record_id = None
                    monthly_record_id = None
                    quarterly_record_id = None
                    exists_daily = False
                    region = ''
                   
                    daily_rec = daily_by_date_full.get(cur)
                    daily_record_id = None
                    if daily_rec:
                        exists_daily = True
                        daily_record_id = getattr(daily_rec, 'id', None)
                        region = getattr(daily_rec, 'region', '') or ''
                        for k in NUMERIC_KEYS:
                            totals[k] = getattr(daily_rec, k, 0) or 0
                        daily_debug.append(f"{cur}: HAS_DAILY (s1_total={totals.get('s1_total', 0)})")
                    else:
                        for (w_start, w_end), weekly_fill in weekly_fill_by_range.items():
                            if w_start <= cur <= w_end:
                                for k in NUMERIC_KEYS:
                                    totals[k] = getattr(weekly_fill, k, 0) or 0
                                filled_by_weekly = True
                                weekly_fill_record_id = getattr(weekly_fill, 'id', None)
                                weekly_record = weekly_record_by_range.get((w_start, w_end))
                                weekly_record_id = getattr(weekly_record, 'id', None) if weekly_record else None
                               
                                is_first_fill_day = (
                                    first_weekly_fill_day_by_id.get(weekly_fill_record_id) == cur
                                )
                               
                                daily_debug.append(f"{cur}: WEEKLY_FILL is_first={is_first_fill_day} (s1_total={totals.get('s1_total', 0)})")
                                break

                        if not filled_by_weekly:
                            for (m_start, m_end), monthly_fill in monthly_fill_by_range.items():
                                if m_start <= cur <= m_end:
                                    for k in NUMERIC_KEYS:
                                        totals[k] = getattr(monthly_fill, k, 0) or 0
                                    filled_by_monthly = True
                                    monthly_fill_record_id = getattr(monthly_fill, 'id', None)
                                    monthly_record = next(
                                        (
                                            r for r in all_monthly_records
                                            if r.period_start <= m_start and r.period_end is not None and r.period_end >= m_end
                                        ),
                                        None
                                    )
                                    monthly_record_id = getattr(monthly_record, 'id', None) if monthly_record else None
                                    is_first_monthly_fill_day = (
                                        first_monthly_fill_day_by_id.get(monthly_fill_record_id) == cur
                                    )
                                    daily_debug.append(f"{cur}: MONTHLY_FILL is_first={is_first_monthly_fill_day} (s1_total={totals.get('s1_total', 0)})")
                                    break

                        if not filled_by_weekly and not filled_by_monthly and quarterly_fill and q_start <= cur <= q_end:
                            for k in NUMERIC_KEYS:
                                totals[k] = getattr(quarterly_fill, k, 0) or 0
                            filled_by_quarterly = True
                            quarterly_fill_record_id = getattr(quarterly_fill, 'id', None)
                            quarterly_record = next(
                                (
                                    r for r in all_quarterly_records
                                    if r.period_start <= q_start and r.period_end is not None and r.period_end >= q_end
                                ),
                                None
                            )
                            quarterly_record_id = getattr(quarterly_record, 'id', None) if quarterly_record else None
                            is_first_quarterly_fill_day = (first_quarterly_fill_day == cur)
                            daily_debug.append(f"{cur}: QUARTERLY_FILL is_first={is_first_quarterly_fill_day} (s1_total={totals.get('s1_total', 0)})")
                   
                    covered_by = None
                    if not exists_daily and not filled_by_weekly and not filled_by_monthly and not filled_by_quarterly:
                        for w_start, w_end in weekly_ranges:
                            if w_start is not None and w_end is not None and w_start <= cur <= w_end:
                                covered_by = 'weekly'
                                break
                        if not covered_by:
                            for m_start, m_end in monthly_ranges:
                                if m_start is not None and m_end is not None and m_start <= cur <= m_end:
                                    covered_by = 'monthly'
                                    break
                        if not covered_by:
                            for q_start_r, q_end_r in quarterly_ranges:
                                if q_start_r is not None and q_end_r is not None and q_start_r <= cur <= q_end_r:
                                    covered_by = 'quarterly'
                                    break
                   
                    daily.append({
                        'period_start': cur.isoformat(),
                        'period_end': cur.isoformat(),
                        'totals': totals,
                        'has_daily': exists_daily,
                        'daily_id': daily_record_id,
                        'filled_by_weekly': filled_by_weekly,
                        'filled_by_monthly': filled_by_monthly,
                        'filled_by_quarterly': filled_by_quarterly,
                        'is_first_fill_day': is_first_fill_day,
                        'is_first_monthly_fill_day': is_first_monthly_fill_day,
                        'is_first_quarterly_fill_day': is_first_quarterly_fill_day,
                        'weekly_fill_record_id': weekly_fill_record_id,
                        'monthly_fill_record_id': monthly_fill_record_id,
                        'quarterly_fill_record_id': quarterly_fill_record_id,
                        'weekly_record_id': weekly_record_id,
                        'monthly_record_id': monthly_record_id,
                        'quarterly_record_id': quarterly_record_id,
                        'covered_by': covered_by,
                        'region': region or default_region or ''
                    })
                cur = cur + timedelta(days=1)
            logger.debug("Daily summary computed for report list")
            logger.debug("Current cursor position and data type verified")
            for k in daily_by_date_full.keys():
                logger.debug("Daily date key processed")
            w_start = q_start - timedelta(days=q_start.weekday())
            while w_start <= q_end:
                w_end = w_start + timedelta(days=5)
                display_start = max(w_start, q_start)
                display_end = min(w_end, q_end)
               
                clipped_ws, clipped_we = get_clipped_week_bounds(w_start, quarter, year)
               
                weekly_snap = weekly_by_range.get((clipped_ws, clipped_we))
                if weekly_snap and not getattr(weekly_snap, 'is_overwritten', False):
                    weekly_snap, _ = _rebuild_weekly_snapshot_from_source(
                        target_user, clipped_ws, clipped_we, quarter, year
                    )
                if weekly_snap:
                    totals = {k: getattr(weekly_snap, k, 0) or 0 for k in NUMERIC_KEYS}
                else:
                    totals = {k: 0 for k in NUMERIC_KEYS}
               
                daily_count = sum(1 for d in all_daily_recs
                                 if display_start <= d['period_start'] <= display_end)
               
                expected_days = 0
                for d in range((display_end - display_start).days + 1):
                    dt = display_start + timedelta(days=d)
                    if dt.weekday() <= 5 and q_start <= dt <= q_end:
                        expected_days += 1
               
                missing_days = max(0, expected_days - daily_count)
               
                weekly_submitted = any(
                    (r.period_start is not None and r.period_start <= display_start and r.period_end is not None and r.period_end >= display_end)
                    for r in all_weekly_records
                )
                covered_by_monthly = any(
                    (fill.period_start <= display_end and fill.period_end is not None and fill.period_end >= display_start)
                    for fill in all_monthly_fills
                ) or any(
                    (r.period_start is not None and r.period_start <= display_end and r.period_end is not None and r.period_end >= display_start)
                    for r in all_monthly_records
                )
                covered_by_quarterly = bool(quarterly_fill) or any(
                    (r.period_start is not None and r.period_start <= display_end and r.period_end is not None and r.period_end >= display_start)
                    for r in all_quarterly_records
                )
               
                region_week = ''
                if weekly_snap:
                    region_week = getattr(weekly_snap, 'region', '') or ''
                if not region_week:
                    for rec in all_daily_recs:
                        if display_start <= rec['period_start'] <= display_end:
                            region_week = rec.get('region', '')
                            break
               
                weekly.append({
                    'period_start': display_start.isoformat(),
                    'period_end': display_end.isoformat(),
                    'totals': totals,
                    'daily_count': daily_count,
                    'expected_days': expected_days,
                    'missing_days': missing_days,
                    'weekly_submitted': weekly_submitted,
                    'covered_by': 'monthly' if covered_by_monthly else ('quarterly' if covered_by_quarterly else ''),
                    'region': region_week or default_region or ''
                })
                w_start = w_start + timedelta(days=7)
           
            m = q_start
            while m <= q_end:
                month_start = date(m.year, m.month, 1)
                if m.month == 12:
                    month_end = date(m.year, 12, 31)
                else:
                    month_end = date(m.year, m.month + 1, 1) - timedelta(days=1)
                if month_end > q_end:
                    month_end = q_end
                if month_start < q_start:
                    month_start = q_start
               
                monthly_snap = monthly_by_range.get((month_start, month_end))
                if monthly_snap and not getattr(monthly_snap, 'is_overwritten', False):
                    monthly_snap, _ = _rebuild_monthly_snapshot_from_source(
                        target_user, month_start, month_end, quarter, year
                    )
                elif not monthly_snap:
                    monthly_snap, _ = _rebuild_monthly_snapshot_from_source(
                        target_user, month_start, month_end, quarter, year
                    )
                if monthly_snap:
                    totals = {k: getattr(monthly_snap, k, 0) or 0 for k in NUMERIC_KEYS}
                else:
                    totals = {k: 0 for k in NUMERIC_KEYS}
               
                daily_count = sum(1 for d in all_daily_recs
                                 if month_start <= d['period_start'] <= month_end)
               
                monthly_submitted = any(
                    (r.period_start is not None and r.period_start <= month_start and r.period_end is not None and r.period_end >= month_end)
                    for r in all_monthly_records
                )
                covered_by_quarterly = bool(quarterly_fill) or any(
                    (r.period_start is not None and r.period_start <= month_start and r.period_end is not None and r.period_end >= month_end)
                    for r in all_quarterly_records
                )
               
                region_month = ''
                if monthly_snap:
                    region_month = getattr(monthly_snap, 'region', '') or ''
                if not region_month:
                    for rec in all_daily_recs:
                        if month_start <= rec['period_start'] <= month_end:
                            region_month = rec.get('region', '')
                            break
               
                monthly.append({
                    'period_start': month_start.isoformat(),
                    'period_end': month_end.isoformat(),
                    'totals': totals,
                    'daily_count': daily_count,
                    'monthly_submitted': monthly_submitted,
                    'covered_by': 'quarterly' if covered_by_quarterly else '',
                    'region': region_month or default_region or ''
                })
               
                if m.month == 12:
                    m = date(m.year + 1, 1, 1)
                else:
                    m = date(m.year, m.month + 1, 1)
           
            if quarterly_snap and not getattr(quarterly_snap, 'is_overwritten', False):
                quarterly_snap, _ = _rebuild_quarterly_snapshot_from_source(target_user, quarter, year)
            elif not quarterly_snap:
                quarterly_snap, _ = _rebuild_quarterly_snapshot_from_source(target_user, quarter, year)

            if quarterly_snap:
                quarterly = {
                    'period_start': q_start.isoformat(),
                    'period_end': q_end.isoformat(),
                    'totals': {k: getattr(quarterly_snap, k, 0) or 0 for k in NUMERIC_KEYS},
                    'submitted': True,
                    'is_snapshot': True,
                    'data_source': 'Quarterly snapshot',
                    'composition': None,
                    'quarter': quarter,
                    'year': year
                }
            else:
                quarterly = {
                    'period_start': q_start.isoformat(),
                    'period_end': q_end.isoformat(),
                    'totals': {k: 0 for k in NUMERIC_KEYS},
                    'submitted': False,
                    'is_snapshot': False,
                    'data_source': 'No data',
                    'composition': None,
                    'quarter': quarter,
                    'year': year
                }

        summary = {
            'quarter_label': quarter,
            'year_label': year,
            'quarter_start': q_start.isoformat() if q_start else None,
            'quarter_end': q_end.isoformat() if q_end else None,
            'daily': daily,
            'weekly': weekly,
            'monthly': monthly,
            'quarterly': quarterly
        }
        context['summary_data'] = summary
    except Exception:
        context['summary_data'] = None
    return render(request, 'qpr/report_list.html', context)


def _qpr_filter_year_options_for_users(users):
    user_ids = []
    for user in users:
        user_id = getattr(user, 'id', None)
        if user_id is not None:
            user_ids.append(user_id)

    raw_year_values = QPRRecord.objects.filter(user_id__in=user_ids).values_list('year', flat=True)
    year_values = []
    seen_years = set()
    for raw_year in raw_year_values:
        normalized_year = str(raw_year or '').strip()
        if normalized_year and normalized_year not in seen_years:
            seen_years.add(normalized_year)
            year_values.append(normalized_year)

    current_year = get_current_year_label()
    if current_year not in seen_years:
        year_values.append(current_year)

    return sorted(year_values, reverse=True)


def _qpr_filter_quarter_options():
    return [
        '30 जून / Jun 30',
        '30 सितंबर / Sep 30',
        '31 दिसंबर / Dec 31',
        '31 मार्च / Mar 31',
    ]


@login_required
def finalize_qpr(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
   
    try:        
        quarter = get_current_quarter()
        year = get_current_year_label()
       
        finalization, created = QPRFinalization.objects.get_or_create(
            user=request.user,
            quarter=quarter,
            year=year
        )
       
        return JsonResponse({
            'success': True,
            'message': f'QPR finalized for {quarter} {year}'
        })
    except Exception:
        app_logger.exception("QPR finalization failed.")
        return JsonResponse({'error': 'Unable to finalize QPR at this time.'}, status=500)


@login_required
def report_detail(request, record_id):
    user_id = request.GET.get('user_id') or None
    is_hod_view = False
    target_user_id = ''

    division_flag = request.GET.get('division')
    if division_flag == '1':
        if not (user_has_role(request.user, 'hod') or user_has_role(request.user, 'admin') or request.user.is_superuser or user_has_role(request.user, 'manager')):
            messages.error(request, 'Unauthorized')
            return redirect('home')

        hod_profile = None
        try:
            if record_id:
                rec = QPRRecord.objects.filter(id=record_id, frequency__iexact='quarterly', is_quarterly_frozen=True).select_related('user').first()
            else:
                rec = None
        except Exception:
            rec = None

        if rec:
            if user_has_role(request.user, 'manager') and not (user_has_role(request.user, 'hod') or user_has_role(request.user, 'admin') or request.user.is_superuser):
                mgr_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
                mgr_office = getattr(mgr_profile, 'office_code', None)
                rec_user_profile = getattr(getattr(rec.user, 'profile', None), 'office_code', None)
                rec_office = getattr(rec, 'officeCode', None) or rec_user_profile
                if not (mgr_office and rec_office and str(mgr_office).strip() == str(rec_office).strip()):
                    messages.error(request, 'Unauthorized')
                    return redirect('home')
            try:
                snap = serialize_qpr_record(rec)
            except Exception:
                snap = None

            try:
                owner_profile = getattr(rec.user, 'profile', None)
                owner_hod_name = (owner_profile.hod_name or owner_profile.name) if owner_profile else None
                owner_hod_name = owner_hod_name.strip() if owner_hod_name else None
                current_quarter = (getattr(rec, 'quarter', None) or request.GET.get('quarter') or get_current_quarter()).strip()
                current_year = (getattr(rec, 'year', None) or request.GET.get('year') or get_current_year_label()).strip()
                try:
                    q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)
                except Exception:
                    q_start = None
                    q_end = None

                expected = {k: 0 for k in NUMERIC_KEYS}
                if owner_hod_name and q_start and q_end:
                    users_under = UserProfile.objects.filter(roles__name='user', hod_name__iexact=owner_hod_name).select_related('user')
                    for p in users_under:
                        try:
                            u = getattr(p, 'user', None)
                            if not u:
                                continue
                            ut = _quarterly_snapshot_totals_for_user(u, current_quarter, current_year)
                            for k in NUMERIC_KEYS:
                                try:
                                    expected[k] += int(ut.get(k, 0) or 0)
                                except Exception:
                                    continue
                        except Exception:
                            continue
                valid_snapshot = False
                if snap is not None:
                    try:
                        all_match = True
                        for k in NUMERIC_KEYS:
                            s_val = int(snap.get(k, 0) or 0)
                            e_val = int(expected.get(k, 0) or 0)
                            if s_val != e_val:
                                all_match = False
                                break
                        if all_match:
                            valid_snapshot = True
                    except Exception:
                        valid_snapshot = False
            except Exception:
                valid_snapshot = False

            if valid_snapshot and snap is not None:
                try:
                    import json as _json
                    initial_qpr_json = _json.dumps(snap, default=str)
                except Exception:
                    initial_qpr_json = '{}'
                return render(request, 'qpr/report_detail.html', {'qpr': snap, 'initial_qpr_json': initial_qpr_json, 'is_division': True})

        hod_profile = getattr(request.user, 'profile', None)
        hod_name_val = None
        if hod_profile:
            hod_name_val = (hod_profile.hod_name or hod_profile.name)
        hod_name_val = hod_name_val.strip() if hod_name_val else None
        if not hod_name_val:
            messages.error(request, 'HOD identity not found')
            return redirect('qpr_hod_dashboard')

        if user_has_role(request.user, 'manager') and not user_has_role(request.user, 'hod') and not (user_has_role(request.user, 'admin') or request.user.is_superuser):
            mgr_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
            mgr_office = getattr(mgr_profile, 'office_code', None)
            hod_office = getattr(hod_profile, 'office_code', None)
            if not (mgr_office and hod_office and str(mgr_office).strip() == str(hod_office).strip()):
                messages.error(request, 'Unauthorized')
                return redirect('home')

        users_under = UserProfile.objects.filter(roles__name='user', hod_name__iexact=hod_name_val).select_related('user')

        current_quarter = (request.GET.get('quarter') or get_current_quarter()).strip()
        current_year = (request.GET.get('year') or get_current_year_label()).strip()

        try:
            q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)
        except Exception:
            current_quarter = get_current_quarter()
            current_year = get_current_year_label()
            q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)

        aggregated: dict[str, int | str] = {k: 0 for k in NUMERIC_KEYS}
        aggregated['quarter'] = current_quarter
        aggregated['year'] = current_year
        aggregated['frequency'] = 'quarterly'
        aggregated['officeName'] = (hod_name_val or '') + " (Division)"
        aggregated['officeCode'] = ''
        aggregated['region'] = ''
        aggregated['phone'] = ''
        aggregated['email'] = ''
        aggregated['s9_date'] = ''
        aggregated['s10_date'] = ''
        aggregated['s12_1'] = ''
        aggregated['s12_2'] = ''
        aggregated['s12_3'] = ''
       
        try:
            record_count = 0
            processed_user_ids = set()
            for profile in users_under:
                try:
                    user_obj = getattr(profile, 'user', None)
                    if not user_obj:
                        continue
                    try:
                        processed_user_ids.add(int(user_obj.id))
                    except Exception:
                        pass
                    logger.debug("Processing user record")
                    user_totals = _quarterly_snapshot_totals_for_user(user_obj, current_quarter, current_year)
                    try:
                        logger.debug("User totals computed for aggregation")
                    except Exception:
                        pass
                    any_nonzero = False
                    for k in NUMERIC_KEYS:
                        try:
                            v = int(user_totals.get(k, 0) or 0)
                            existing_value = int(aggregated.get(k, 0) or 0)
                            aggregated[k] = existing_value + v
                            if v != 0:
                                any_nonzero = True
                        except Exception:
                            continue
                    if any_nonzero:
                        record_count += 1
                except Exception:
                    continue

            try:
                logger.debug("Final aggregated values computed")
            except Exception:
                pass
        except Exception:
            pass

        aggregated_qpr: dict[str, Any] = {
            'quarter': aggregated.get('quarter'),
            'year': aggregated.get('year'),
            'frequency': aggregated.get('frequency'),
            'officeName': aggregated.get('officeName'),
            'officeCode': aggregated.get('officeCode'),
            'region': aggregated.get('region'),
            'phone': aggregated.get('phone'),
            'email': aggregated.get('email'),
        }
        for k in NUMERIC_KEYS:
            aggregated_qpr[k] = aggregated.get(k, 0)
        aggregated_qpr['s9_date'] = aggregated.get('s9_date', '')
        aggregated_qpr['s10_date'] = aggregated.get('s10_date', '')
        aggregated_qpr['s12_1'] = aggregated.get('s12_1', '')
        aggregated_qpr['s12_2'] = aggregated.get('s12_2', '')
        aggregated_qpr['s12_3'] = aggregated.get('s12_3', '')

        try:
            aggregated_qpr['cumulative'] = {'quarterly': {k: aggregated.get(k, 0) for k in NUMERIC_KEYS}}
            initial_qpr_json = json.dumps(aggregated_qpr)
        except Exception:
            initial_qpr_json = '{}'

        return render(request, 'qpr/report_detail.html', {'qpr': aggregated_qpr, 'initial_qpr_json': initial_qpr_json, 'is_division': True})

    if user_id:
        try:
            uid = int(user_id)
            target = CustomUser.objects.filter(id=uid).first()
        except Exception:
            target = None
        if not target:
            messages.error(request, 'User not found')
            return redirect('qpr_report_list')
        if target.id != request.user.id:
            allowed = False
            if user_has_role(request.user, 'admin') or request.user.is_superuser:
                allowed = True

            if not allowed and user_has_role(request.user, 'hod'):
                allowed = True
                requester_hod = (getattr(request.user.profile, 'hod_name', None) or getattr(request.user.profile, 'name', None))
                target_hod = (getattr(target, 'profile', None) and (getattr(target.profile, 'hod_name', None) or getattr(target.profile, 'name', None)))
                if requester_hod and target_hod and str(requester_hod).strip().lower() != str(target_hod).strip().lower():
                    messages.error(request, 'Unauthorized')
                    return redirect('qpr_hod_dashboard')

            if not allowed and user_has_role(request.user, 'manager'):
                mgr_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
                mgr_office = getattr(mgr_profile, 'office_code', None)
                tgt_profile = getattr(target, 'profile', None)
                tgt_office = getattr(tgt_profile, 'office_code', None)
                if mgr_office and tgt_office and str(mgr_office).strip() == str(tgt_office).strip():
                    allowed = True

            if not allowed:
                messages.error(request, 'Unauthorized')
                return redirect('home')
        is_hod_view = (target.id != request.user.id)
        target_user_id = target.id

    record_json = '{}'
    try:
        rec = QPRRecord.objects.filter(pk=record_id, user=target if 'target' in locals() and target is not None else request.user).first()
        if rec:
            try:
                import json as _json
                record_data = serialize_qpr_record(rec)
                view_as = (request.GET.get('view_as') or '').lower()
                try:
                    ps = getattr(rec, 'period_start', None)
                    pe = getattr(rec, 'period_end', None) or ps
                    if ps:
                        record_data.setdefault('cumulative', {})
                        if view_as == 'weekly' or view_as == 'weekly' or True:
                            try:
                                wk_start, wk_end = get_clipped_week_bounds(ps, rec.quarter, rec.year)
                               
                                weekly_snap = WeeklySnapshot.objects.filter(
                                    user=rec.user,
                                    quarter=rec.quarter,
                                    year=rec.year,
                                    period_start=wk_start,
                                    period_end=wk_end
                                ).first()
                                if weekly_snap and not getattr(weekly_snap, 'is_overwritten', False):
                                    weekly_snap, _ = _rebuild_weekly_snapshot_from_source(
                                        rec.user, wk_start, wk_end, rec.quarter, rec.year
                                    )
                               
                                if weekly_snap:
                                    wk_tot = {k: getattr(weekly_snap, k, 0) or 0 for k in NUMERIC_KEYS}
                                else:
                                    wk_tot = _aggregate_records_with_fallback(rec.user, wk_start, wk_end, preferred='weekly')
                               
                                record_data['cumulative']['weekly'] = wk_tot
                                try:
                                    s12_1_txt = _aggregate_section11_text_for_range(rec.user, wk_start, wk_end, 'innovative_work', source_frequency='all')
                                    s12_2_txt = _aggregate_section11_text_for_range(rec.user, wk_start, wk_end, 'special_events', source_frequency='all')
                                    s12_3_txt = _aggregate_section11_text_for_range(rec.user, wk_start, wk_end, 'hindi_medium_works', source_frequency='all')
                                    record_data.setdefault('cumulative_text', {})
                                    record_data['cumulative_text']['weekly'] = {'s12_1': s12_1_txt, 's12_2': s12_2_txt, 's12_3': s12_3_txt}
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        try:
                            m_start = date(ps.year, ps.month, 1)
                            if ps.month == 12:
                                m_end = date(ps.year, 12, 31)
                            else:
                                m_end = date(ps.year, ps.month + 1, 1) - timedelta(days=1)
                           
                            monthly_snap = MonthlySnapshot.objects.filter(
                                user=rec.user,
                                quarter=rec.quarter,
                                year=rec.year,
                                period_start=m_start,
                                period_end=m_end
                            ).first()
                            if monthly_snap and not getattr(monthly_snap, 'is_overwritten', False):
                                monthly_snap, _ = _rebuild_monthly_snapshot_from_source(
                                    rec.user, m_start, m_end, rec.quarter, rec.year
                                )
                            elif not monthly_snap:
                                monthly_snap, _ = _rebuild_monthly_snapshot_from_source(
                                    rec.user, m_start, m_end, rec.quarter, rec.year
                                )
                           
                            if monthly_snap:
                                m_tot = {k: getattr(monthly_snap, k, 0) or 0 for k in NUMERIC_KEYS}
                            else:
                                m_tot = _aggregate_records_with_fallback(rec.user, m_start, m_end, preferred='monthly')
                           
                            record_data['cumulative']['monthly'] = m_tot
                            try:
                                s12_1_txt = _aggregate_section11_text_for_range(rec.user, m_start, m_end, 'innovative_work', source_frequency='all')
                                s12_2_txt = _aggregate_section11_text_for_range(rec.user, m_start, m_end, 'special_events', source_frequency='all')
                                s12_3_txt = _aggregate_section11_text_for_range(rec.user, m_start, m_end, 'hindi_medium_works', source_frequency='all')
                                record_data.setdefault('cumulative_text', {})
                                record_data['cumulative_text']['monthly'] = {'s12_1': s12_1_txt, 's12_2': s12_2_txt, 's12_3': s12_3_txt}
                            except Exception:
                                pass
                        except Exception:
                            pass
                        try:
                            q_start, q_end = _quarter_label_to_daterange(rec.quarter, rec.year or get_current_year_label())                            
                            quarter_snap = QuarterlySnapshot.objects.filter(
                                user=rec.user,
                                quarter=rec.quarter,
                                year=rec.year or get_current_year_label()
                            ).first()
                            if quarter_snap and not getattr(quarter_snap, 'is_overwritten', False):
                                quarter_snap, _ = _rebuild_quarterly_snapshot_from_source(
                                    rec.user, rec.quarter, rec.year or get_current_year_label()
                                )
                           
                            if quarter_snap:
                                q_tot = {k: getattr(quarter_snap, k, 0) or 0 for k in NUMERIC_KEYS}
                            else:
                                q_tot = _aggregate_records_with_fallback(rec.user, q_start, q_end, preferred='quarterly')
                           
                            record_data['cumulative']['quarterly'] = q_tot
                            try:
                                s12_1_txt = _aggregate_section11_text_for_range(rec.user, q_start, q_end, 'innovative_work', source_frequency='all')
                                s12_2_txt = _aggregate_section11_text_for_range(rec.user, q_start, q_end, 'special_events', source_frequency='all')
                                s12_3_txt = _aggregate_section11_text_for_range(rec.user, q_start, q_end, 'hindi_medium_works', source_frequency='all')
                                record_data.setdefault('cumulative_text', {})
                                record_data['cumulative_text']['quarterly'] = {'s12_1': s12_1_txt, 's12_2': s12_2_txt, 's12_3': s12_3_txt}
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass
                record_json = _json.dumps(record_data, default=str)
                try:
                    _add_qpr_edit_flags(record_data, rec, request.user, rec.user)
                    record_json = _json.dumps(record_data, default=str)
                except Exception:
                    pass
            except Exception:
                record_json = '{}'
    except Exception:
        record_json = '{}'

    return render(request, 'qpr/report_detail.html', {'record_id': record_id, 'is_hod_view': is_hod_view, 'target_user_id': target_user_id, 'record_json': record_json})

@login_required
def hod_detail_list(request):
    if not user_has_role(request.user, 'hod'):
        return redirect('/')
   
    hod_profile = getattr(request.user, 'profile', None)
    hod_name = (hod_profile.hod_name or hod_profile.name) if hod_profile else None
    hod_name = hod_name.strip() if hod_name else None

    if hod_name:
        user_role_q = Q(roles__name='user') | Q(user__roles__name='user')
        user_ids = UserProfile.objects.filter(
            user_role_q & Q(hod_name__iexact=hod_name) & Q(approval_status__iexact='approved')
        ).values_list('id',flat=True).distinct()
        users_under_hod = UserProfile.objects.filter(id__in = user_ids).select_related('user')
    else:
        users_under_hod = UserProfile.objects.filter(user=request.user, approval_status__iexact='approved').select_related('user')
   
    selected_quarter = (request.GET.get('quarter') or get_current_quarter()).strip()
    selected_year = (request.GET.get('year') or get_current_year_label()).strip()
    try:
        _quarter_label_to_daterange(selected_quarter, selected_year)
    except Exception:
        selected_quarter = get_current_quarter()
        selected_year = get_current_year_label()

    users_data = []
    current_quarter = selected_quarter
    current_year = selected_year
    today = timezone.localdate()
    for user_profile in users_under_hod:
        user = user_profile.user
        qpr_records = user.qpr_records.all()
        office_code = ''
        office_name = ''
        if qpr_records.exists():
            first_qpr = qpr_records.first()
            office_code = first_qpr.officeCode
            office_name = first_qpr.officeName

        emp_code_val = (user_profile.employee_code or '').strip()
        emp_record = None
        if emp_code_val:
            try:
                emp_int = int(emp_code_val)
                emp_record = Employee.objects.filter(empcode=emp_int).first()
            except Exception:
                emp_record = Employee.objects.filter(empcode=emp_code_val).first()

        display_name = user_profile.name or user.get_full_name() or ''
        if not display_name or display_name.strip().lower() in ['', 'none']:
            if emp_record and emp_record.ename:
                display_name = emp_record.ename
            else:
                display_name = user.username

        office_name_val = user_profile.office_name or office_name or ''
        office_code_val = user_profile.office_code or office_code or ''
        if (not office_name_val or office_name_val.strip() == '') and emp_record:
            office_name_val = getattr(emp_record, 'hname', '') or office_name_val

        has_pending = ManagerRequest.objects.filter(hod=user, request_type='qpr', status='pending').exists()
        current_qpr = qpr_records.filter( quarter=current_quarter, year=current_year ).first()
        qpr_complete_flag = current_qpr.is_submitted if current_qpr else False
        try:
            submitted_today = user.qpr_records.filter(frequency__iexact='daily', period_start=today, is_submitted=True).exists()
        except Exception:
            submitted_today = False
        users_data.append({
            'profile': user_profile,
            'user': user,
            'employee_code': user_profile.employee_code,
            'name': display_name,
            'office_code': office_code_val or 'Not Set',
            'office_name': office_name_val or 'Not Set',
            'profile_complete': user_profile.profile_updated,
            'qpr_complete': current_qpr.is_submitted if current_qpr else False,
            'qpr_record_id': current_qpr.id if current_qpr else None,
            'has_pending_edit_request': has_pending,
            'submitted_today': submitted_today,
        })
   
    profile_change_requests = ProfileChangeRequest.objects.filter(
        hod=request.user,
        status__in=['pending', 'approved', 'rejected']
    ).select_related('profile__user').order_by('-requested_at')

    all_users_ids = list(set([up.user.id for up in users_under_hod if getattr(up, 'user', None)]))
    if user_has_role(request.user, 'user') and request.user.id not in all_users_ids:
        all_users_ids.append(request.user.id)
   
    total_users = len(all_users_ids)
    finalized_count = 0
    if total_users > 0:
        finalized_count = QPRFinalization.objects.filter(
            user_id__in=all_users_ids,
            quarter=current_quarter,
            year=current_year
        ).values('user_id').distinct().count()
   
    all_finalized = (total_users > 0 and finalized_count == total_users)
    today = timezone.localdate()
    q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)
    is_future_period = q_start > today
    is_current_period = q_start <= today <= q_end
    if is_future_period:
        can_freeze_division = False
        freeze_disabled_reason = 'This quarter has not started yet'
    elif is_current_period:
        can_freeze_division = all_finalized
        freeze_disabled_reason = '' if all_finalized else 'All employees must finalize their QPR first'
    else:
        can_freeze_division = True
        freeze_disabled_reason = ''
    report_query = urlencode({'quarter': current_quarter, 'year': current_year})

    context = {
        'users_data': users_data,
        'hod_name': hod_name,
        'current_quarter': current_quarter,
        'current_year': current_year,
        'quarter_filter': current_quarter,
        'year_filter': current_year,
        'quarter_options': _qpr_filter_quarter_options(),
        'year_options': _qpr_filter_year_options_for_users([up.user for up in users_under_hod if getattr(up, 'user', None)]),
        'report_query': report_query,
        'profile_change_requests': profile_change_requests,
        'finalized_count': finalized_count,
        'total_users': total_users,
        'all_finalized': all_finalized,
        'is_current_period': is_current_period,
        'is_future_period': is_future_period,
        'can_freeze_division': can_freeze_division,
        'freeze_disabled_reason': freeze_disabled_reason,
    }
   
    response = render(request, 'qpr/hod_detail_list.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
def toggle_freeze_qpr(request, qpr_record_id):
    if not user_has_role(request.user, 'hod'):
        return redirect('/')
   
    if request.method != 'POST':
        return redirect('qpr_hod_detail_list')
   
    try:
        qpr_record = QPRRecord.objects.get(id=qpr_record_id, frequency='quarterly')
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Quarterly record not found'}, status=404)
   
    hod_profile = getattr(request.user, 'profile', None)
    hod_name = (hod_profile.hod_name or hod_profile.name) if hod_profile else None
   
    if hod_name:
        user_profile = getattr(qpr_record.user, 'profile', None)
        record_hod_name = (user_profile.hod_name or user_profile.name) if user_profile else None
        if record_hod_name != hod_name.strip():
            return JsonResponse({'error': 'Unauthorized'}, status=403)
   
    today = date.today()
    quarter_end_dates = get_quarter_end_dates()
   
    is_at_quarter_end = today >= quarter_end_dates['current']
   
    if qpr_record.is_quarterly_frozen:
        qpr_record.is_quarterly_frozen = False
        message = 'Quarterly report unfrozen'
    else:
        if is_at_quarter_end:
            qpr_record.is_quarterly_frozen = True
            message = 'Quarterly report frozen'
        else:
            days_until_end = (quarter_end_dates['current'] - today).days
            message = f'Can only freeze at quarter end (in {days_until_end} days)'
            return JsonResponse({'error': message}, status=400)
   
    qpr_record.save()
   
    return redirect('qpr_hod_detail_list')

@login_required
def freeze_division_snapshot(request):
    if not user_has_role(request.user, 'hod'):
        messages.error(request, 'Unauthorized access')
        return redirect('qpr_hod_detail_list')

    if request.method != 'POST':
        messages.error(request, 'Invalid request method')
        return redirect('qpr_hod_detail_list')

    hod_profile = getattr(request.user, 'profile', None)
    hod_name = (hod_profile.hod_name or hod_profile.name) if hod_profile else None
    current_quarter = (request.POST.get('quarter') or get_current_quarter()).strip()
    current_year = (request.POST.get('year') or get_current_year_label()).strip()
    try:
        _quarter_label_to_daterange(current_quarter, current_year)
    except Exception:
        current_quarter = get_current_quarter()
        current_year = get_current_year_label()

    existing = QPRRecord.objects.filter(user=request.user, frequency__iexact='quarterly', quarter=current_quarter, year=current_year, is_quarterly_frozen=True)
    if existing.exists():
        messages.error(request, 'You have already frozen for this quarter')
        return redirect(f"{reverse('qpr_hod_detail_list')}?{urlencode({'quarter': current_quarter, 'year': current_year})}")

    if hod_name:
        user_role_q = Q(roles__name='user') | Q(user__roles__name='user')
        users_under_hod = UserProfile.objects.filter(user_role_q & Q(hod_name__iexact=hod_name)).select_related('user').distinct()
    else:
        users_under_hod = UserProfile.objects.filter(user=request.user).select_related('user')

    user_ids = list(set(users_under_hod.values_list('user__id', flat=True)))
    if user_has_role(request.user, 'user') and request.user.id not in user_ids:
        user_ids.append(request.user.id)
    q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)
    today = timezone.localdate()
    if q_start > today:
        messages.error(request, 'This quarter has not started yet. Division QPR can be frozen only when the quarter is current or in the past.')
        return redirect(f"{reverse('qpr_hod_detail_list')}?{urlencode({'quarter': current_quarter, 'year': current_year})}")

    is_current_period = q_start <= today <= q_end
    if is_current_period:

        finalized_count = QPRFinalization.objects.filter(
            user_id__in=user_ids,
            quarter=current_quarter,
            year=current_year
        ).values('user_id').distinct().count()
        if not user_ids or finalized_count != len(user_ids):
            messages.error(request, 'All employees must finalize their QPR before freezing the current quarter.')
            return redirect(f"{reverse('qpr_hod_detail_list')}?{urlencode({'quarter': current_quarter, 'year': current_year})}")

    totals = {k: 0 for k in NUMERIC_KEYS}
    record_count = 0
    try:
        try:
            q_start, q_end = _quarter_label_to_daterange(current_quarter, current_year)
        except Exception:
            q_start = None
            q_end = None

        assert q_start is not None and q_end is not None
        if user_ids and q_start and q_end:
            for uid in user_ids:
                try:
                    u = CustomUser.objects.filter(id=uid).first()
                    if not u:
                        continue
                    user_totals = _quarterly_snapshot_totals_for_user(u, current_quarter, current_year)
                    any_nonzero = False
                    for k in NUMERIC_KEYS:
                        try:
                            v = int(user_totals.get(k, 0) or 0)
                            totals[k] += v
                            if v != 0:
                                any_nonzero = True
                        except Exception:
                            continue
                    if any_nonzero:
                        record_count += 1
                except Exception:
                    continue
    except Exception:
        totals = {k: 0 for k in NUMERIC_KEYS}

    officeName = getattr(hod_profile, 'office_name', '') or ''
    officeCode = getattr(hod_profile, 'office_code', '') or ''

    qpr_fields = {
        'user': request.user,
        'frequency': 'quarterly',
        'quarter': current_quarter,
        'year': current_year,
        'is_quarterly_frozen': True,
        'is_submitted': True,
        'officeName': officeName,
        'officeCode': officeCode,
    }

    new_rec = QPRRecord.objects.create(**qpr_fields)


    try:
        _save_section_data(new_rec, totals)
    except Exception:
        try:
            new_rec.delete()
        except Exception:
            pass
        messages.error(request, 'Failed to save aggregated section data')
        return redirect(f"{reverse('qpr_hod_detail_list')}?{urlencode({'quarter': current_quarter, 'year': current_year})}")

    # DEBUG: verify saved snapshot sections
    try:
        nr = QPRRecord.objects.filter(id=new_rec.id).first()
        s1 = Section1FilesData.objects.filter(qpr_record=nr).first()
        s2 = Section2MeetingsData.objects.filter(qpr_record=nr).first()
        logger.debug("Snapshot section data verified")
        if s1:
            logger.debug("Section 1 data verified")
        if s2:
            logger.debug("Section 2 meeting data verified")
    except Exception:
        pass

    messages.success(request, 'Division quarter frozen successfully. Any further changes in QPR will not be shown in the state aggregation.')
    return redirect(f"{reverse('qpr_hod_detail_list')}?{urlencode({'quarter': current_quarter, 'year': current_year})}")

def _get_missing_days_context(user, frequency, selected_date, quarter=None, year=None):
    if frequency not in ['weekly', 'monthly', 'quarterly']:
        return {'missing_days': [], 'has_fill': False, 'fill_fields_count': 0, 'message': ''}
   
    try:
        period_start, period_end = compute_period(frequency, selected_date, quarter, year)
        missing_days = _get_missing_days_in_range(user, period_start, period_end)
        has_fill = False
        fill_fields_count = 0
       
        if frequency == 'weekly':
            fill = WeeklyFill.objects.filter(
                user=user,
                period_start=period_start,
                period_end=period_end,
                quarter=quarter or '',
                year=year or ''
            ).first()
            if fill:
                has_fill = True
                for key in NUMERIC_KEYS:
                    if getattr(fill, key, None):
                        fill_fields_count += 1
       
        elif frequency == 'monthly':
            fill = MonthlyFill.objects.filter(
                user=user,
                period_start=period_start,
                period_end=period_end,
                quarter=quarter or '',
                year=year or ''
            ).first()
            if fill:
                has_fill = True
                for key in NUMERIC_KEYS:
                    if getattr(fill, key, None):
                        fill_fields_count += 1
       
        elif frequency == 'quarterly':
            fill = QuarterlyFill.objects.filter(
                user=user,
                quarter=quarter or '',
                year=year or ''
            ).first()
            if fill:
                has_fill = True
                for key in NUMERIC_KEYS:
                    if getattr(fill, key, None):
                        fill_fields_count += 1
       
        if missing_days:
            day_names = [d.strftime('%a') for d in missing_days]
            message = f"Filling {len(missing_days)} missing day{'s' if len(missing_days) != 1 else ''} ({', '.join(day_names)}) for {frequency} of {period_start.strftime('%d-%m-%Y')}"
        else:
            message = f"All days covered for this {frequency}. No missing days to fill."
       
        return {
            'missing_days': [d.isoformat() for d in missing_days],
            'has_fill': has_fill,
            'fill_fields_count': fill_fields_count,
            'message': message,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat()
        }
   
    except Exception:
        logger.error("Failed to get missing days context.")
        return {'missing_days': [], 'has_fill': False, 'fill_fields_count': 0, 'message': '', 'error': "An unexpected error occurred."}
def _count_fill_fields(fill):
    if not fill:
        return 0
    return sum(1 for key in NUMERIC_KEYS if getattr(fill, key, None))


def _missing_days_client_source(user):
    daily_dates = list(
        QPRRecord.objects.filter(
            user=user,
            is_submitted=True,
            frequency__iexact='daily',
            period_start__isnull=False,
        ).values_list('period_start', flat=True)
    )
    weekly_fills = [
        {
            'period_start': fill.period_start.isoformat(),
            'period_end': fill.period_end.isoformat(),
            'quarter': fill.quarter or '',
            'year': fill.year or '',
            'fill_fields_count': _count_fill_fields(fill),
        }
        for fill in WeeklyFill.objects.filter(user=user)
    ]
    monthly_fills = [
        {
            'period_start': fill.period_start.isoformat(),
            'period_end': fill.period_end.isoformat(),
            'quarter': fill.quarter or '',
            'year': fill.year or '',
            'fill_fields_count': _count_fill_fields(fill),
        }
        for fill in MonthlyFill.objects.filter(user=user)
    ]
    quarterly_fills = [
        {
            'period_start': fill.period_start.isoformat(),
            'period_end': fill.period_end.isoformat(),
            'quarter': fill.quarter or '',
            'year': fill.year or '',
            'fill_fields_count': _count_fill_fields(fill),
        }
        for fill in QuarterlyFill.objects.filter(user=user)
    ]
    return {
        'submitted_daily_dates': [d.isoformat() for d in daily_dates if d],
        'fills': {
            'weekly': weekly_fills,
            'monthly': monthly_fills,
            'quarterly': quarterly_fills,
        },
    }

def _validate_details_for_missing_dates(user, period_start, period_end, details, entry_type):
    try:
        missing_dates = _get_missing_days_in_range(user, period_start, period_end)
       
        if not missing_dates:
            error_msg = (
                f"Cannot submit {entry_type} entry: No missing dates in this period. "
                f"All working days {period_start} to {period_end} already have daily submissions."
            )
            return False, [], error_msg
       
        has_values = any(
            details.get(key) for key in NUMERIC_KEYS
            if details.get(key)
        )
        if not has_values:
            error_msg = (
                f"Cannot submit {entry_type} entry: No data provided. "
                f"Please enter values for at least one field."
            )
            return False, missing_dates, error_msg
       
        return True, missing_dates, ""
       
    except Exception:
        logger.exception("Validation error for entry")
        error_msg = f"An error occurred while validating {entry_type} entry"
        return False, [], error_msg


def _create_or_update_weekly_fill(user, period_start, period_end, details, quarter, year):
    try:
        if period_start and period_end:
            normalized_start, normalized_end = get_clipped_week_bounds(period_start, quarter, year)
        else:
            normalized_start = period_start
            normalized_end = period_end
       
        is_valid, missing_dates, error_msg = _validate_details_for_missing_dates(
            user, normalized_start, normalized_end, details, 'weekly'
        )
        if not is_valid:
            logger.warning("Weekly Fill validation failed for user %s", user.id)
            return None, error_msg
       
        fill, _ = WeeklyFill.objects.get_or_create(
            user=user,
            period_start=normalized_start,
            period_end=normalized_end,
            quarter=quarter,
            year=year
        )
       
        for key in NUMERIC_KEYS:
            value = details.get(key)
            try:
                value = int(value) if value else None
            except (ValueError, TypeError):
                value = None
            if hasattr(fill, key):
                setattr(fill, key, value)
       
        fill.save()
        logger.info("Weekly Fill created for user %s", user.id)
        return fill, ""
    except Exception:
        logger.exception("Failed to create WeeklyFill")
        return None, "An error occurred while creating the weekly fill. Please try again."


def _create_or_update_monthly_fill(user, period_start, period_end, details, quarter, year):
    try:
        is_valid, missing_dates, error_msg = _validate_details_for_missing_dates(
            user, period_start, period_end, details, 'monthly'
        )
        if not is_valid:
            logger.warning("Monthly Fill validation failed for user %s", user.id)
            return None, error_msg
       
        fill, _ = MonthlyFill.objects.get_or_create(
            user=user,
            period_start=period_start,
            period_end=period_end,
            quarter=quarter,
            year=year
        )
       
        for key in NUMERIC_KEYS:
            value = details.get(key)
            try:
                value = int(value) if value else None
            except (ValueError, TypeError):
                value = None
            if hasattr(fill, key):
                setattr(fill, key, value)
       
        fill.save()
        logger.info("Monthly Fill created for user %s", user.id)
        return fill, ""
    except Exception:
        logger.exception("Failed to create MonthlyFill")
        return None, "An error occurred while creating the monthly fill. Please try again."


def _create_or_update_quarterly_fill(user, details, quarter, year, period_start=None, period_end=None):
    try:
        if not period_start or not period_end:
            error_msg = "Cannot create quarterly fill: period_start and period_end required"
            logger.error("Failed to determine period dates for quarterly fill")
            return None, error_msg
       
        is_valid, missing_dates, error_msg = _validate_details_for_missing_dates(
            user, period_start, period_end, details, 'quarterly'
        )
        if not is_valid:
            logger.warning("Quarterly Fill validation failed for user %s", user.id)
            return None, error_msg
       
        fill, _ = QuarterlyFill.objects.get_or_create(
            user=user,
            quarter=quarter,
            year=year,
            defaults={
                'period_start': period_start,
                'period_end': period_end
            }
        )
       
        for key in NUMERIC_KEYS:
            value = details.get(key)
            try:
                value = int(value) if value else None
            except (ValueError, TypeError):
                value = None
            if hasattr(fill, key):
                setattr(fill, key, value)
       
        fill.save()
        logger.info(f"Quarterly Fill created for user {user.id} for quarter {quarter} year {year}")
        return fill, ""
    except Exception:
        logger.exception("Failed to create QuarterlyFill")
        return None, "An error occurred while creating the quarterly fill. Please try again."

def _get_missing_days_in_range(user, start_date, end_date):  
    all_dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() != 6:
            all_dates.append(current)
        current += timedelta(days=1)
   
    submitted_dates = set(
        QPRRecord.objects.filter(
            user=user,
            frequency__iexact='daily',
            is_submitted=True,
            period_start__in=all_dates
        ).values_list('period_start', flat=True)
    )
   
    return [d for d in all_dates if d not in submitted_dates]


def _extract_details_from_record(qpr_record):
    data = serialize_qpr_record(qpr_record)
    return {k: (data.get(k) or 0) for k in NUMERIC_KEYS}


def _sum_daily_in_range(user, start_date, end_date):
    total = {k: 0 for k in NUMERIC_KEYS}
    try:
        daily_records = QPRRecord.objects.filter(
            user=user,
            frequency__iexact='daily',
            is_submitted=True,
            period_start__gte=start_date,
            period_start__lte=end_date
        ).values_list('id')
       
        for (record_id,) in daily_records:
            record = QPRRecord.objects.get(id=record_id)
            data = _extract_details_from_record(record)
            for k in NUMERIC_KEYS:
                total[k] = (total[k] or 0) + (data.get(k) or 0)
    except Exception:
        logger.exception("Error aggregating daily records in range")
    return total


def _sum_weekly_fill_in_range(user, start_date, end_date):
    total = {k: 0 for k in NUMERIC_KEYS}
    try:
        fills = WeeklyFill.objects.filter(
            user=user,
            period_start__gte=start_date,
            period_start__lte=end_date
        )
        for fill in fills:
            for k in NUMERIC_KEYS:
                total[k] = (total[k] or 0) + (getattr(fill, k, 0) or 0)
    except Exception:
        logger.exception("Error aggregating weekly fills in range")
    return total


def _sum_weekly_snapshots_in_month(user, month_start, month_end, quarter, year):
    total = {k: 0 for k in NUMERIC_KEYS}
    try:
        snapshots = WeeklySnapshot.objects.filter(
            user=user,
            quarter=quarter,
            year=year,
            period_start__gte=month_start,
            period_end__lte=month_end
        )
        snapshot_ranges = set()
        for snap in snapshots:
            snapshot_ranges.add((snap.period_start, snap.period_end))
            for k in NUMERIC_KEYS:
                total[k] = (total[k] or 0) + (getattr(snap, k, 0) or 0)

        daily_records = QPRRecord.objects.filter(
            user=user,
            frequency__iexact='daily',
            is_submitted=True,
            period_start__gte=month_start,
            period_start__lte=month_end,
        )
        for record in daily_records:
            week_start, week_end = get_clipped_week_bounds(record.period_start, quarter, year)
            if (
                week_start >= month_start
                and week_end <= month_end
                and (week_start, week_end) in snapshot_ranges
            ):
                continue
            data = _extract_details_from_record(record)
            for k in NUMERIC_KEYS:
                total[k] = (total[k] or 0) + (data.get(k, 0) or 0)

        edge_fills = WeeklyFill.objects.filter(
            user=user,
            quarter=quarter,
            year=year,
            period_start__lte=month_end,
            period_end__gte=month_start,
        )
        for fill in edge_fills:
            if (
                fill.period_start >= month_start
                and fill.period_end <= month_end
                and (fill.period_start, fill.period_end) in snapshot_ranges
            ):
                continue

            missing_dates = _get_missing_days_in_range(user, fill.period_start, fill.period_end)
            month_missing_dates = [d for d in missing_dates if month_start <= d <= month_end]
            if not missing_dates or not month_missing_dates:
                continue

            numerator = len(month_missing_dates)
            denominator = len(missing_dates)
            for k in NUMERIC_KEYS:
                value = getattr(fill, k, 0) or 0
                total[k] = (total[k] or 0) + round(value * numerator / denominator)
    except Exception:
        logger.exception("Error aggregating weekly snapshots in month")
    return total


def _sum_monthly_snapshots_in_quarter(user, quarter, year):
    total = {k: 0 for k in NUMERIC_KEYS}
    try:
        snapshots = MonthlySnapshot.objects.filter(
            user=user,
            quarter=quarter,
            year=year
        )
        for snap in snapshots:
            for k in NUMERIC_KEYS:
                total[k] = (total[k] or 0) + (getattr(snap, k, 0) or 0)
    except Exception:
        logger.exception("Error aggregating monthly snapshots in quarter")
    return total


def _get_or_create_weekly_snapshot_with_sum(user, period_start, period_end, quarter, year):
    if period_start:
        normalized_start, normalized_end = get_clipped_week_bounds(period_start, quarter, year)
    else:
        normalized_start = period_start
        normalized_end = period_end
   
    snapshot, created = WeeklySnapshot.objects.get_or_create(
        user=user,
        period_start=normalized_start,
        period_end=normalized_end,
        quarter=quarter,
        year=year,
        defaults={'is_overwritten': False}
    )
   
    if created:
        daily_sum = _sum_daily_in_range(user, normalized_start, normalized_end)
        fill_sum = _sum_weekly_fill_in_range(user, normalized_start, normalized_end)
       
        for k in NUMERIC_KEYS:
            val = (daily_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
            setattr(snapshot, k, val)
        snapshot.save()
        logger.info(f"WeeklySnapshot created for user={user.id}: {normalized_start} to {normalized_end}")    
    return snapshot, created


def _get_or_create_monthly_snapshot_with_sum(user, period_start, period_end, quarter, year):

    snapshot, created = MonthlySnapshot.objects.get_or_create(
        user=user,
        period_start=period_start,
        period_end=period_end,
        quarter=quarter,
        year=year,
        defaults={'is_overwritten': False}
    )
   
    if created:
        weekly_sum = _sum_weekly_snapshots_in_month(user, period_start, period_end, quarter, year)
       
        monthly_fill = MonthlyFill.objects.filter(
            user=user,
            period_start=period_start,
            period_end=period_end,
            quarter=quarter,
            year=year
        ).first()
       
        fill_sum = {}
        if monthly_fill:
            fill_sum = {k: (getattr(monthly_fill, k, 0) or 0) for k in NUMERIC_KEYS}
        else:
            fill_sum = {k: 0 for k in NUMERIC_KEYS}
       
        for k in NUMERIC_KEYS:
            val = (weekly_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
            setattr(snapshot, k, val)
        snapshot.save()
        logger.info(f"MonthlySnapshot created for user={user.id}: {period_start} to {period_end}")    
    return snapshot, created


def _get_or_create_quarterly_snapshot_with_sum(user, quarter, year, period_start, period_end):

    snapshot, created = QuarterlySnapshot.objects.get_or_create(
        user=user,
        quarter=quarter,
        year=year,
        defaults={
            'period_start': period_start,
            'period_end': period_end,
            'is_overwritten': False
        }
    )
   
    if created:
        monthly_sum = _sum_monthly_snapshots_in_quarter(user, quarter, year)
       
        quarterly_fill = QuarterlyFill.objects.filter(
            user=user,
            quarter=quarter,
            year=year
        ).first()
       
        fill_sum = {}
        if quarterly_fill:
            fill_sum = {k: (getattr(quarterly_fill, k, 0) or 0) for k in NUMERIC_KEYS}
        else:
            fill_sum = {k: 0 for k in NUMERIC_KEYS}
       
        for k in NUMERIC_KEYS:
            val = (monthly_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
            setattr(snapshot, k, val)
        snapshot.save()
        logger.info(f"QuarterlySnapshot created for user={user.id} for quarter={quarter} year={year}")    
    return snapshot, created


def _increment_snapshot_by_delta(snapshot, delta):
    if getattr(snapshot, 'is_overwritten', False):
        return False
    for k in NUMERIC_KEYS:
        current = getattr(snapshot, k, 0) or 0
        setattr(snapshot, k, current + (delta.get(k, 0) or 0))
    snapshot.save()
    return True

def _rebuild_weekly_snapshot_from_source(user, period_start, period_end, quarter, year):
    try:
        if period_start and period_end:
            normalized_start, normalized_end = get_clipped_week_bounds(period_start, quarter, year)
        else:
            normalized_start = period_start
            normalized_end = period_end
       
        daily_sum = _sum_daily_in_range(user, normalized_start, normalized_end)
        fill_sum = _sum_weekly_fill_in_range(user, normalized_start, normalized_end)
       
        total = {}
        for k in NUMERIC_KEYS:
            total[k] = (daily_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
       
        snapshot, created = WeeklySnapshot.objects.get_or_create(
            user=user,
            period_start=normalized_start,
            period_end=normalized_end,
            quarter=quarter,
            year=year,
            defaults={'is_overwritten': False}
        )

        if not created and getattr(snapshot, 'is_overwritten', False):
            return snapshot, False
       
        was_updated = False
        for k in NUMERIC_KEYS:
            new_val = total.get(k, 0) or 0
            old_val = getattr(snapshot, k, 0) or 0
            if new_val != old_val:
                setattr(snapshot, k, new_val)
                was_updated = True
       
        if was_updated:
            snapshot.save()
            logger.debug("WeeklySnapshot recalculated for user %s", user.id)
       
        return snapshot, was_updated
       
    except Exception:
        logger.exception("Failed to rebuild weekly snapshot")
        return None, False


def _rebuild_monthly_snapshot_from_source(user, period_start, period_end, quarter, year):
    try:
        weekly_ranges = set(
            QPRRecord.objects.filter(
                user=user,
                is_submitted=True,
                frequency__iexact='weekly',
                quarter=quarter,
                year=year,
                period_start__gte=period_start,
                period_start__lte=period_end
            ).values_list('period_start', 'period_end')
        )
        daily_dates = QPRRecord.objects.filter(
            user=user,
            is_submitted=True,
            frequency__iexact='daily',
            period_start__gte=period_start,
            period_start__lte=period_end
        ).values_list('period_start', flat=True)
        for daily_date in daily_dates:
            weekly_ranges.add(get_clipped_week_bounds(daily_date, quarter, year))
        weekly_ranges.update(
            WeeklyFill.objects.filter(
                user=user,
                quarter=quarter,
                year=year,
                period_start__gte=period_start,
                period_start__lte=period_end
            ).values_list('period_start', 'period_end')
        )
        for w_start, w_end in weekly_ranges:
            _rebuild_weekly_snapshot_from_source(user, w_start, w_end, quarter, year)

        for weekly_snapshot in WeeklySnapshot.objects.filter(
            user=user,
            quarter=quarter,
            year=year,
            period_start__gte=period_start,
            period_start__lte=period_end
        ):
            if not getattr(weekly_snapshot, 'is_overwritten', False):
                _rebuild_weekly_snapshot_from_source(
                    user, weekly_snapshot.period_start, weekly_snapshot.period_end, quarter, year
                )

        weekly_sum = _sum_weekly_snapshots_in_month(user, period_start, period_end, quarter, year)
       
        monthly_fill = MonthlyFill.objects.filter(
            user=user,
            period_start=period_start,
            period_end=period_end,
            quarter=quarter,
            year=year
        ).first()
       
        fill_sum = {k: (getattr(monthly_fill, k, 0) or 0) for k in NUMERIC_KEYS} if monthly_fill else {k: 0 for k in NUMERIC_KEYS}
       
        total = {}
        for k in NUMERIC_KEYS:
            total[k] = (weekly_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
       
        snapshot, created = MonthlySnapshot.objects.get_or_create(
            user=user,
            period_start=period_start,
            period_end=period_end,
            quarter=quarter,
            year=year,
            defaults={'is_overwritten': False}
        )

        if not created and getattr(snapshot, 'is_overwritten', False):
            return snapshot, False
       
        was_updated = False
        for k in NUMERIC_KEYS:
            new_val = total.get(k, 0) or 0
            old_val = getattr(snapshot, k, 0) or 0
            if new_val != old_val:
                setattr(snapshot, k, new_val)
                was_updated = True
       
        if was_updated:
            snapshot.save()
            logger.debug("MonthlySnapshot recalculated for user %s", user.id)
       
        return snapshot, was_updated
       
    except Exception:
        logger.exception("Failed to rebuild monthly snapshot")
        return None, False


def _rebuild_quarterly_snapshot_from_source(user, quarter, year):
    try:
        try:
            q_start, q_end = _quarter_label_to_daterange(quarter, year)
            for monthly_snapshot in MonthlySnapshot.objects.filter(
                user=user,
                quarter=quarter,
                year=year,
                period_start__gte=q_start,
                period_end__lte=q_end
            ):
                if not getattr(monthly_snapshot, 'is_overwritten', False):
                    _rebuild_monthly_snapshot_from_source(
                        user, monthly_snapshot.period_start, monthly_snapshot.period_end, quarter, year
                    )
        except Exception:
            logger.exception("Failed to refresh monthly snapshots before quarterly rebuild")

        monthly_sum = _sum_monthly_snapshots_in_quarter(user, quarter, year)
       
        quarterly_fill = QuarterlyFill.objects.filter(
            user=user,
            quarter=quarter,
            year=year
        ).first()
       
        fill_sum = {k: (getattr(quarterly_fill, k, 0) or 0) for k in NUMERIC_KEYS} if quarterly_fill else {k: 0 for k in NUMERIC_KEYS}
       
        total = {}
        for k in NUMERIC_KEYS:
            total[k] = (monthly_sum.get(k, 0) or 0) + (fill_sum.get(k, 0) or 0)
       
        snapshot = QuarterlySnapshot.objects.filter(
            user=user, quarter=quarter, year=year
        ).first()
       
        if not snapshot:
            try:
                period_start, period_end = _quarter_label_to_daterange(quarter, year)
            except:
                period_start, period_end = None, None
           
            snapshot = QuarterlySnapshot.objects.create(
                user=user,
                quarter=quarter,
                year=year,
                period_start=period_start,
                period_end=period_end,
                is_overwritten=False
            )
        elif getattr(snapshot, 'is_overwritten', False):
            return snapshot, False
       
        was_updated = False
        for k in NUMERIC_KEYS:
            new_val = total.get(k, 0) or 0
            old_val = getattr(snapshot, k, 0) or 0
            if new_val != old_val:
                setattr(snapshot, k, new_val)
                was_updated = True
       
        if was_updated:
            snapshot.save()
            logging.debug(f"QuarterlySnapshot recalculated for user {user.id}: Q{quarter} {year}")
       
        return snapshot, was_updated
    except Exception:
        logging.exception("Error rebuilding quarterly snapshot from source")
        return None, False


def _detect_event_type(qpr_record):
    if not qpr_record or not qpr_record.id:
        return 'insert'
   
    try:
        existing = QPRRecord.objects.filter(id=qpr_record.id).exists()
        return 'edit' if existing else 'insert'
    except:
        return 'insert'


def _trigger_aggregation_chain_optimized(qpr_record, event_type=None, old_values=None):
    if not qpr_record or not qpr_record.is_submitted:
        return {'success': False, 'error': 'Invalid or unsubmitted QPR record'}
   
    frequency = (qpr_record.frequency or '').lower()
    user = qpr_record.user
    result = {'success': True, 'errors': [], 'fills_created': []}
   
    try:
        if not event_type:
            event_type = _detect_event_type(qpr_record)
       
        try:
            new_values = _extract_details_from_record(qpr_record)
        except Exception:
            logger.exception("Failed to extract details from record")
            new_values = {k: 0 for k in NUMERIC_KEYS}
            result['errors'].append("Unable to extract record details")
       
        if frequency == 'daily':
            ps, pe = qpr_record.period_start, qpr_record.period_end
           
            if event_type == 'insert':
                weekly_snapshot, weekly_created = _get_or_create_weekly_snapshot_with_sum(
                    user, ps, pe, qpr_record.quarter, qpr_record.year
                )
                if not weekly_created:
                    _increment_snapshot_by_delta(weekly_snapshot, new_values)
               
                monthly_ps, monthly_pe = compute_period('monthly', selected_date=ps)
                monthly_snapshot, monthly_created = _get_or_create_monthly_snapshot_with_sum(
                    user, monthly_ps, monthly_pe, qpr_record.quarter, qpr_record.year
                )
                if not monthly_created:
                    _increment_snapshot_by_delta(monthly_snapshot, new_values)
               
                quarterly_snapshot, quarterly_created = _get_or_create_quarterly_snapshot_with_sum(
                    user, qpr_record.quarter, qpr_record.year,
                    qpr_record.period_start or monthly_ps, qpr_record.period_end or monthly_pe
                )
                if not quarterly_created:
                    _increment_snapshot_by_delta(quarterly_snapshot, new_values)
               
                logger.debug("Daily insert processed for user %s", user.id)
           
            else:
                if old_values is None:
                    old_values = {k: 0 for k in NUMERIC_KEYS}
                if new_values is None:
                    new_values = {k: 0 for k in NUMERIC_KEYS}
               
                actual_delta = {k: (new_values.get(k, 0) or 0) - (old_values.get(k, 0) or 0)
                               for k in NUMERIC_KEYS}
               
                weekly_snapshot, weekly_created = _get_or_create_weekly_snapshot_with_sum(
                    user, ps, pe, qpr_record.quarter, qpr_record.year
                )
                if not weekly_created:
                    _increment_snapshot_by_delta(weekly_snapshot, actual_delta)
               
                monthly_ps, monthly_pe = compute_period('monthly', selected_date=ps)
                monthly_snapshot, monthly_created = _get_or_create_monthly_snapshot_with_sum(
                    user, monthly_ps, monthly_pe, qpr_record.quarter, qpr_record.year
                )
                if not monthly_created:
                    _increment_snapshot_by_delta(monthly_snapshot, actual_delta)
               
                quarterly_snapshot, quarterly_created = _get_or_create_quarterly_snapshot_with_sum(
                    user, qpr_record.quarter, qpr_record.year,
                    qpr_record.period_start or monthly_ps, qpr_record.period_end or monthly_pe
                )
                if not quarterly_created:
                    _increment_snapshot_by_delta(quarterly_snapshot, actual_delta)
               
                logger.debug("Daily edit processed for user %s", user.id)
       
        elif frequency == 'weekly':
            ps, pe = qpr_record.period_start, qpr_record.period_end
           
            fill= _create_or_update_weekly_fill(
                user, ps, pe, new_values, qpr_record.quarter, qpr_record.year
            )
            if fill:
                result['fills_created'].append('weekly')
           
            weekly_snapshot, weekly_updated = _rebuild_weekly_snapshot_from_source(
                user, ps, pe, qpr_record.quarter, qpr_record.year
            )
           
            if weekly_updated or fill:
                monthly_ps, monthly_pe = compute_period('monthly', selected_date=ps)
                monthly_snapshot, _ = _rebuild_monthly_snapshot_from_source(
                    user, monthly_ps, monthly_pe, qpr_record.quarter, qpr_record.year
                )
               
                quarterly_snapshot, _ = _rebuild_quarterly_snapshot_from_source(
                    user, qpr_record.quarter, qpr_record.year
                )
                logger.debug("Weekly aggregation: rebuilt chain for user %s", user.id)
            else:
                logger.debug("Weekly aggregation: no changes for user %s", user.id)
       
        elif frequency == 'monthly':
            ps, pe = qpr_record.period_start, qpr_record.period_end
           
            fill = _create_or_update_monthly_fill(
                user, ps, pe, new_values, qpr_record.quarter, qpr_record.year
            )
            if fill:
                result['fills_created'].append('monthly')
           
            monthly_snapshot, monthly_updated = _rebuild_monthly_snapshot_from_source(
                user, ps, pe, qpr_record.quarter, qpr_record.year
            )
           
            if monthly_updated or fill:
                quarterly_snapshot, _ = _rebuild_quarterly_snapshot_from_source(
                    user, qpr_record.quarter, qpr_record.year
                )
                logger.debug("Monthly aggregation: rebuilt chain for user %s", user.id)
            else:
                logger.debug("Monthly aggregation: no changes for user %s", user.id)
       
        elif frequency == 'quarterly':
            fill = _create_or_update_quarterly_fill(
                user, new_values, qpr_record.quarter, qpr_record.year,
                qpr_record.period_start, qpr_record.period_end
            )
            if fill:
                result['fills_created'].append('quarterly')
           
            quarterly_snapshot, quarterly_updated = _rebuild_quarterly_snapshot_from_source(
                user, qpr_record.quarter, qpr_record.year
            )
           
            if quarterly_updated or fill:
                logger.debug("Quarterly aggregation: updated for user %s", user.id)
            else:
                logger.debug("Quarterly aggregation: no changes for user %s", user.id)
       
    except Exception:
        logger.exception("Error in optimized aggregation chain")
        result['errors'].append("An error occurred while processing the aggregation chain.")
        result['success'] = False
   
    return result

@login_required
def qpr_records_view(request):
    records = QPRRecord.objects.filter(user=request.user).order_by('-id')
    return render(request, 'qpr_records.html', {
        'records': records
    })


@login_required
def qpr_user_report_list(request):
    records = QPRRecord.objects.filter(user=request.user, frequency__iexact='quarterly').order_by('-period_start')
    return render(request, 'qpr/user_report_list.html', {
        'records': records
    })


@login_required
def manager_qpr_list(request):
    records = ManagerQPR.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'qpr/manager_qpr_list.html', {'records': records})


@login_required
def admin_qpr_list(request):
    records = AdminQPR.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'qpr/admin_qpr_list.html', {'records': records})


@login_required
def qpr_save_record(request):
    if request.method != 'POST':
        return redirect('qpr_records')

    data = request.POST

    def reject_to_qpr_form(message):
        messages.error(request, message)
        request.session['qpr_popup_error'] = message
        return redirect('qpr_form')

    role_form = (data.get('role_form') or '').strip().lower()
    if role_form:
        try:
            if role_form == 'manager':
                return redirect('manager_qpr_form')
            if role_form == 'admin':
                return redirect('admin_qpr_form')
        except Exception:
            return redirect('qpr_records')

    try:
        year = (data.get('year') or '').strip()

        today = timezone.localdate()
        current_start = today.year if today.month >= 4 else today.year - 1

        if year:
            try:
                selected_start = int(year.split('-')[0])
            except:
                messages.error(request, "Invalid year format")
                return redirect('qpr_records')

            if selected_start > current_start:
                messages.error(request, "Future financial year not allowed")
                return redirect('qpr_records')

        record_id = data.get('id')
        details = json.loads(data.get('details', '{}'))

        if record_id:
            record = get_object_or_404(QPRRecord, pk=record_id, user=request.user)
            snapshot_edit_scope = (data.get('snapshot_edit_scope') or '').strip().lower()
            if snapshot_edit_scope in SNAPSHOT_EDIT_SCOPES:
                if data.get('status', 'Submitted') != 'Submitted':
                    messages.error(request, "Snapshot edits must be submitted. Draft is not available for snapshot overwrites.")
                    return redirect('qpr_report_list')

                approved_request = _approved_qpr_edit_request(request.user, record, snapshot_edit_scope)
                if not approved_request:
                    messages.error(request, "Snapshot edit approval not found.")
                    return redirect('qpr_report_list')

                snapshot = _overwrite_snapshot_from_details(record, snapshot_edit_scope, details)
                if not snapshot:
                    messages.error(request, "Unable to update snapshot.")
                    return redirect('qpr_report_list')

                _refresh_parent_snapshots_after_overwrite(record, snapshot_edit_scope)
                approved_request.status = 'temp use'
                approved_request.save(update_fields=['status', 'updated_at'])
                EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record.pk,
                    status='pending'
                ).update(status='rejected')
                messages.success(request, "Snapshot values updated successfully.")
                return redirect('qpr_report_list')

            base_approved_request = None
            if record.is_submitted:
                base_approved_request = _approved_qpr_edit_request(request.user, record, 'base')
            if record.is_submitted and not base_approved_request:
                messages.error(request, "QPR edit approval not found for this submitted record.")
                return redirect('qpr_report_list')
           
            old_values = None
            if record.is_submitted:
                try:
                    old_values = _extract_details_from_record(record)
                except Exception:
                    old_values = None

            record.officeName = data.get('officeName', '')
            record.officeCode = (data.get('officeCode', '') or '').replace('*', '')
            record.region = data.get('region', '')
            record.quarter = data.get('quarter', '')
            record.year = data.get('year', '')
            record.status = data.get('status', 'Draft')
            record.phone = data.get('phone', '')
            record.email = data.get('email', '')
            record.frequency = data.get('frequency', 'quarterly')
            record.is_submitted = (record.status == 'Submitted')

            allowed_quarters = get_allowed_quarters(record.year)
            if record.quarter and record.quarter not in allowed_quarters:
                messages.error(request, "Invalid quarter selection")
                return redirect('qpr_records')

            ps, pe = record.period_start, record.period_end
            if not ps or not pe:
                try:
                    ps, pe = _quarter_label_to_daterange(record.quarter, record.year)
                except:
                    ps, pe = None, None

            if ps and pe and is_period_overlapping(request.user, ps, pe, exclude_id=record.pk, new_frequency=record.frequency):
                return reject_to_qpr_form("This QPR has already been filled for the selected period.")

            record.period_start = ps
            record.period_end = pe
            record.save()

            if getattr(request.user, 'is_edit_allowed', False):
                request.user.is_edit_allowed = False
                request.user.save(update_fields=['is_edit_allowed'])

            if record.is_submitted:
                ManagerRequest.objects.filter(hod=request.user, request_type='qpr', status='approved').delete()

                try:
                    logger.debug("Before update edit requests for user %s record %s", request.user.id, record.pk)
                except Exception:
                    pass

                for edit_request in EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record.pk,
                    status='approved'
                ):
                    requested_scope = ((edit_request.requested_data or {}).get('edit_scope') or '').lower()
                    if requested_scope not in SNAPSHOT_EDIT_SCOPES:
                        edit_request.status = 'temp use'
                        edit_request.save(update_fields=['status', 'updated_at'])
                EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record.pk,
                    status='pending'
                ).update(status='rejected')

                try:
                    logger.debug("After update edit requests for user %s record %s", request.user.id, record.pk)
                except Exception:
                    pass

            _save_section_data(record, details)
           
            if record.is_submitted:
                agg_result = _trigger_aggregation_chain_optimized(record, event_type='edit', old_values=old_values)
                if agg_result and not agg_result.get('success', True):
                    error_details = ' | '.join(agg_result.get('errors', []))
                    messages.warning(request, f"Record saved with aggregation notes: {error_details}")
                elif agg_result:
                    fills_created = ', '.join(agg_result.get('fills_created', []))
                    if fills_created:
                        messages.info(request, f"Record submitted with {fills_created} fill(s) created")

        else:
            is_submitted = (data.get('status', 'Draft') == 'Submitted')

            frequency = (data.get('frequency') or 'daily').strip().lower()
            selected_date_str = (data.get('selected_date') or '').strip()
            quarter = data.get('quarter', '').strip()
            year = data.get('year', '').strip() or None

            if frequency not in {'daily', 'weekly', 'monthly', 'quarterly'}:
                messages.error(request, "Invalid frequency")
                return redirect('qpr_records')

            if frequency in ['daily', 'weekly', 'monthly', 'quarterly'] and not selected_date_str:
                messages.error(request, "Date is required")
                return redirect('qpr_records')

            today = timezone.localdate()

            selected_date = None
            if selected_date_str:
                try:
                    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                except:
                    messages.error(request, "Invalid date")
                    return redirect('qpr_records')

            if selected_date:
                if frequency == 'daily' and selected_date.weekday() == 6:
                    messages.error(request, "Sunday not allowed")
                    return redirect('qpr_records')

                if selected_date > today:
                    messages.error(request, "Too far in future")
                    return redirect('qpr_records')

                try:
                    cur_q_start, _ = _get_quarter_range_for_date(today)
                    sel_q_start, _ = _get_quarter_range_for_date(selected_date)
                    if sel_q_start > cur_q_start:
                        messages.error(request, "Future quarter not allowed")
                        return redirect('qpr_records')
                except:
                    pass

            if selected_date:
                quarter = _quarter_label_for_date(selected_date)
                year = _financial_year_for_date(selected_date)

            ps, pe = compute_period(
                frequency,
                selected_date=selected_date,
                quarter=quarter,
                year=year
            )

            if frequency in {'weekly', 'monthly', 'quarterly'}:
                if not selected_date and ps and _is_future_quarter(ps, today=today):
                    messages.error(request, "Future quarter not allowed")
                    return redirect('qpr_records')

                if selected_date and _is_date_in_current_system_quarter(selected_date, today=today):
                    if not _current_quarter_aggregate_fill_allowed(frequency, selected_date):
                        messages.error(request, _current_quarter_fill_error(frequency))
                        return redirect('qpr_form')

            if ps and pe and is_period_overlapping(request.user, ps, pe, new_frequency=frequency):
                return reject_to_qpr_form("This QPR has already been filled for the selected period.")

            allowed_quarters = get_allowed_quarters(year)
            if quarter and quarter not in allowed_quarters:
                messages.error(request, f"Invalid quarter: {allowed_quarters}")
                return redirect('qpr_records')

            exists = QPRRecord.objects.filter(
                user=request.user,
                frequency__iexact=frequency,
                period_start=ps,
                is_submitted=True
            )

            if quarter:
                exists = exists.filter(quarter=quarter)
                if year:
                    exists = exists.filter(year=year)

            if exists.exists():
                return reject_to_qpr_form("This QPR has already been filled for the selected period.")

            record = QPRRecord.objects.create(
                user=request.user,
                officeName=data.get('officeName', ''),
                officeCode=(data.get('officeCode', '') or '').replace('*', ''),
                region=data.get('region', ''),
                quarter=quarter,
                year=year,
                status=data.get('status', 'Draft'),
                frequency=frequency,
                period_start=ps,
                period_end=pe,
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                is_submitted=is_submitted
            )

            _save_section_data(record, details)
           
            if record.is_submitted:
                agg_result = _trigger_aggregation_chain_optimized(record, event_type='insert')
                if agg_result and not agg_result.get('success', True):
                    error_details = ' | '.join(agg_result.get('errors', []))
                    messages.warning(request, f"Record saved with aggregation notes: {error_details}")
                elif agg_result:
                    fills_created = ', '.join(agg_result.get('fills_created', []))
                    if fills_created:
                        messages.info(request, f"Record submitted with {fills_created} fill(s) created")

        messages.success(request, "Saved successfully")
        form_type = (data.get('form_type') or '').strip().lower()
        if form_type == 'manager':
            return redirect('manager_qpr_list')
        elif form_type == 'admin':
            return redirect('admin_qpr_list')
        else:
            return redirect('qpr_report_list')

    except Exception:
        logger.error("Failed to save.", exc_info=True)
        safe_error_msg = "An unexpected error occurred while saving. Please try again."
        messages.error(request, safe_error_msg)
        return redirect('qpr_records')


@login_required
def qpr_delete_record(request, id):
    if request.method == "POST":
        QPRRecord.objects.filter(pk=id, user=request.user).delete()
        messages.success(request, "Deleted successfully")
    return redirect('qpr_records')

@login_required
def snapshot_edit(request, quarter, year):
    try:
        q_label = str(quarter).strip().upper()
        y_label = str(year).strip()
       
        if not q_label.startswith('Q') or not q_label[1:].isdigit():
            messages.error(request, "Invalid quarter format")
            return redirect('qpr_report_list')
       
        try:
            q_start, q_end = _quarter_label_to_daterange(q_label, y_label)
        except:
            messages.error(request, "Invalid quarter/year")
            return redirect('qpr_report_list')
       
        snapshot, created = QuarterlySnapshot.objects.get_or_create(
            user=request.user,
            quarter=q_label,
            year=y_label,
            defaults={
                'period_start': q_start,
                'period_end': q_end,
                'is_overwritten': False
            }
        )
       
        if request.method == 'GET':
            context = {
                'quarter': q_label,
                'year': y_label,
                'period_start': q_start,
                'period_end': q_end,
                'is_overwritten': snapshot.is_overwritten,
                'overwritten_at': snapshot.overwritten_at
            }
           
            for key in NUMERIC_KEYS:
                context[key] = getattr(snapshot, key, 0) or 0
           
            return render(request, 'qpr/snapshot_edit.html', context)
       
        elif request.method == 'POST':
            data = request.POST
           
            try:
                for key in NUMERIC_KEYS:
                    value = data.get(key, '')
                    try:
                        value = int(value) if value else None
                    except (ValueError, TypeError):
                        value = None
                    setattr(snapshot, key, value)
               
                snapshot.is_overwritten = True
                snapshot.overwritten_at = now()
                snapshot.save()
               
                logger.info("Snapshot edited for user %s", request.user.id)
                messages.success(request, f"Snapshot for {q_label} {y_label} has been edited and locked from auto-aggregation.")
                return redirect('qpr_report_list')
               
            except Exception:
                logger.error("Failed to save snapshot.", exc_info=True)
                safe_error_msg = "An unexpected error occurred while saving the snapshot. Please try again."
                messages.error(request, safe_error_msg)
                return redirect('qpr_report_list')
       
        else:
            messages.error(request, "Invalid request method")
            return redirect('qpr_report_list')
           
    except Exception:
        logger.exception("Error in snapshot_edit view")
        messages.error(request, "An error occurred while editing the snapshot.")
        return redirect('qpr_report_list')

@login_required
def print_qpr_report(request, record_id):
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('qpr_report_list')
   
    if not (
        record.user == request.user or
        user_has_role(request.user, ['manager', 'admin']) or
        request.user.is_superuser
    ):
        return redirect('dashboard')

    data = serialize_qpr_record(record)
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
           
            if not request_type or not record_id:
                return JsonResponse({'error': 'Missing required fields'}, status=400)
           
            if request_type == 'qpr':
                try:
                    record = QPRRecord.objects.get(pk=record_id, user=request.user)
                except QPRRecord.DoesNotExist:
                    return JsonResponse({'error': 'Record not found'}, status=404)
               
                existing = EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    status__in=['pending', 'approved']
                ).first()
               
                if existing:
                    return JsonResponse({'error': 'Request already exists with status: ' + existing.status}, status=400)
               
                edit_req = EditRequest.objects.create(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    reason=reason,
                    status='pending'
                )
               
                manager_office = record.officeCode
                managers = UserProfile.objects.filter(
                    office_code=manager_office,
                    roles__name='manager'
                ).select_related('user')
               
                for profile in managers:
                    try:
                        msg = f"Employee {request.user.get_full_name() or request.user.username} has requested permission to edit their QPR submission.\n\nReason: {reason}"
                        #send_system_email(
                        #    profile.user,
                        #    request,
                        #    'manager_alert',
                        #    extra_context={'body_text': msg, 'subject': 'QPR Edit Request'}
                        #)
                    except Exception:
                        pass
               
                return JsonResponse({'success': True, 'message': 'Edit request submitted to manager'})
           
            admin_users = User.objects.filter(profile__roles__name='admin')
            for admin_user in admin_users:
                ManagerRequest.objects.create(hod=request.user, user=admin_user, request_type=request_type, reason=f"Edit request: {reason}")
            return JsonResponse({'success': True, 'message': 'Request sent'})
        except Exception:
            logger.exception("Failed to edit snapshot")
            return JsonResponse({'success': False, 'error': 'Unable to save changes'}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
def request_profile_edit(request):
    lang = request.session.get('lang', 'en')
   
    if request.method == 'POST':
        try:
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
                'username': request.POST.get('username', ''),
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
           
            admins = CustomUser.objects.filter(roles__name='admin', is_active=True)
            for admin in admins:
                msg = f"User {request.user.username} ({request.user.profile.employee_code}) has requested to edit their profile."
                #send_system_email(admin, request, 'manager_alert', extra_context={'body_text': msg})
           
            return redirect('qpr_user_profile')
        except Exception:
            messages.error(request, translate_text("Error submitting request.", lang))
            return redirect('qpr_user_profile')
   
    context = {'profile': request.user.profile, 'current_lang': lang}
    return render(request, 'qpr/request_profile_edit.html', context)


@login_required
def request_qpr_edit(request, record_id):
    lang = request.session.get('lang', 'en')
   
    try:
        qpr_record = QPRRecord.objects.get(id=record_id, user=request.user)
    except QPRRecord.DoesNotExist:
        messages.error(request, translate_text("QPR record not found.", lang))
        return redirect('qpr_report_list')
   
    if qpr_record.frequency == 'quarterly' and qpr_record.is_quarterly_frozen:
        messages.error(request, translate_text("This quarterly report is frozen and cannot be edited.", lang))
        return redirect('qpr_report_detail', record_id=record_id)
   
    if request.method == 'POST':
        try:
            reason = request.POST.get('reason', '')
            edit_scope = (request.POST.get('edit_scope') or '').strip().lower()
            if edit_scope not in SNAPSHOT_EDIT_SCOPES:
                edit_scope = ''
            if edit_scope and not _snapshot_edit_request_allowed(qpr_record, edit_scope):
                messages.error(request, translate_text("Edit requests for this QPR can be made only on or after the period end date.", lang))
                return redirect('qpr_report_detail', record_id=record_id)
           
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
                if edit_scope:
                    ps, pe = _snapshot_bounds_for_record(qpr_record, edit_scope)
                    qpr_data.update({
                        'edit_scope': edit_scope,
                        'period_start': ps.isoformat() if ps else '',
                        'period_end': pe.isoformat() if pe else '',
                    })
               
                EditRequest.objects.create(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    requested_data=qpr_data,
                    reason=reason,
                    status='pending'
                )
                messages.success(request, translate_text("QPR edit request submitted to manager for approval.", lang))
               
                manager_office = qpr_record.officeCode
                managers = UserProfile.objects.filter(
                    office_code=manager_office,
                    roles__name='manager'
                ).select_related('user')
                for profile in managers:
                    msg = f"User {request.user.username} ({request.user.profile.employee_code}) has requested to edit QPR for {qpr_record.quarter}."
                    #send_system_email(profile.user, request, 'manager_alert', extra_context={'body_text': msg})
           
            return redirect('qpr_report_detail', record_id=record_id)
        except Exception:
            messages.error(request, translate_text("Error submitting request.", lang))
            return redirect('qpr_report_detail', record_id=record_id)
   
    context = {'qpr_record': qpr_record, 'current_lang': lang}
    return render(request, 'qpr/request_qpr_edit.html', context)


@login_required
def admin_edit_requests(request):
    if not user_has_role(request.user, ['admin']):
        return redirect('/')
    lang = request.session.get('lang', 'en')
    admin_state = request.user.profile.office_state
   
    status_filter = request.GET.get('status', 'pending')
    request_type_filter = request.GET.get('type', '')
   
    edit_requests = EditRequest.objects.filter(
        user__profile__office_state=admin_state
    ).select_related('user', 'approved_by')
   
    if status_filter:
        edit_requests = edit_requests.filter(status=status_filter)
   
    if request_type_filter:
        edit_requests = edit_requests.filter(request_type=request_type_filter)
   
    context = {
        'edit_requests': edit_requests,
        'status_filter': status_filter,
        'request_type_filter': request_type_filter,
        'statuses': [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('temp use', 'Temp Use')],
        'types': [('profile', 'Profile'), ('qpr', 'QPR')],
        'current_lang': lang,
    }
    return render(request, 'qpr/admin_edit_requests.html', context)


@login_required
def approve_edit_request(request, request_id):
    if not user_has_role(request.user, 'manager'):
        return redirect('/')
    lang = request.session.get('lang', 'en')
   
    try:
        edit_request = EditRequest.objects.get(id=request_id)
    except EditRequest.DoesNotExist:
        messages.error(request, translate_text("Request not found.", lang))
        return redirect('manager_dashboard')
   
    if request.method == 'POST':
        try:
            admin_notes = request.POST.get('admin_notes', '')
           
            edit_request.status = 'approved'
            edit_request.approved_by = request.user
            edit_request.approved_at = now()
            edit_request.admin_notes = admin_notes
            edit_request.save()            
            msg = f"Your {edit_request.get_request_type_display().lower()} edit request has been approved."
            if admin_notes:
                msg += f"\n\nAdmin Notes: {admin_notes}"
            #send_system_email(
            #    edit_request.user,
            #    request,
            #    'manager_alert',
            #    extra_context={'body_text': msg, 'subject': 'Edit Request Approved'}
            #)
           
            messages.success(request, translate_text("Edit request approved.", lang))
            return redirect('manager_dashboard')
        except Exception:
            logger.exception("Failed to approve edit request")
            messages.error(request, 'Unable to approve request. Please try again.')
            return redirect('manager_dashboard')
   
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/approve_edit_request.html', context)


@login_required
def reject_edit_request(request, request_id):
    if not user_has_role(request.user, 'manager'):
        return redirect('/')
    lang = request.session.get('lang', 'en')
   
    try:
        edit_request = EditRequest.objects.get(id=request_id)
    except EditRequest.DoesNotExist:
        messages.error(request, translate_text("Request not found.", lang))
        return redirect('manager_dashboard')
   
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
            msg = f"Your {edit_request.get_request_type_display().lower()} edit request has been rejected.\n\nReason: {admin_notes}"
            #send_system_email(
            #    edit_request.user,
            #    request,
            #    'manager_alert',
            #    extra_context={'body_text': msg, 'subject': 'Edit Request Rejected'}
            #)
           
            messages.success(request, translate_text("Edit request rejected.", lang))
            return redirect('manager_dashboard')
        except Exception:
            logger.exception("Failed to reject edit request")
            messages.error(request, 'Unable to reject request. Please try again.')
            return redirect('manager_dashboard')
   
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/reject_edit_request.html', context)


def send_reminder_email(request, user_id):
    user_profile = getattr(request.user, 'profile', None)
    if not user_profile or not user_profile.roles.filter(name='hod').exists():
        return redirect('/')
       
    if request.method == 'POST':
        target_user = get_object_or_404(CustomUser, id=user_id)
        lang = request.session.get('lang', 'en')
        target_profile = getattr(target_user, 'profile', None)
        if target_profile and target_profile.hod_name == user_profile.hod_name:
            #send_system_email(target_user, request, 'reminder')
            messages.success(request, translate_text(f"Reminder email sent successfully to {target_user.username}.", lang))
        else:
            messages.error(request, translate_text("Unauthorized action.", lang))
           
    return redirect('qpr_hod_detail_list')

@login_required
def export_employee_pdf(request):
    if request.session.get('active_role') != 'user':
        return redirect('dashboard')

    try:
        profile = getattr(request.user, 'profile', None)

        if profile and profile.employee_code:
            user_empcode = int(profile.employee_code)
        else:
            user_empcode = int(request.user.username)

    except (ValueError, TypeError):
        messages.error(request, "Invalid employee code.")
        return redirect('dashboard')

    employees = Employee.objects.filter(empcode=user_empcode, status='submitted')
    lang = request.GET.get('lang', 'en')

    # Translation dictionary
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
            Paragraph(t(emp.highest_exam), cell_style),
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

    elements = [
        Paragraph(title_text, title_style),
        Paragraph(f"Generated on: {date.today().strftime('%d %B %Y')}", subtitle_style),
        Spacer(1, 4*mm),
        table,
    ]

    doc.build(elements)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='employee_records.pdf')


@login_required
def manager_report(request):
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    manager_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
    office_code = getattr(manager_profile, 'office_code', None)
    raw_quarter = (request.GET.get('quarter') or get_current_quarter()).strip()
    raw_year = (request.GET.get('year') or get_current_year_label()).strip()

    # Remove dangerous structural characters and escape HTML
    for ch in ('<', '>', '"', "'"):
        if ch in raw_quarter:
            raw_quarter = raw_quarter.replace(ch, '')
        if ch in raw_year:
            raw_year = raw_year.replace(ch, '')

    current_quarter = escape(raw_quarter)
    current_year = escape(raw_year)

    try:
        _quarter_label_to_daterange(current_quarter, current_year)
    except Exception:
        current_quarter = get_current_quarter()
        current_year = get_current_year_label()

    def _employee_master_for_profile(profile):
        employee_code = (getattr(profile, 'employee_code', '') or '').strip()
        if not employee_code:
            return None
        try:
            return EmployeeMaster.objects.filter(empcode=int(employee_code)).first()
        except (TypeError, ValueError):
            return None

    def _profile_identity(profile):
        user_obj = getattr(profile, 'user', None)
        employee_master = _employee_master_for_profile(profile)
        employee_obj = getattr(profile, 'employee', None)
        full_name = (user_obj.get_full_name() or '').strip() if user_obj else ''
        username = (getattr(user_obj, 'username', '') or '').strip()
        name = (
            (getattr(profile, 'name', '') or '').strip()
            or (getattr(employee_master, 'name', '') or '').strip()
            or (getattr(employee_obj, 'ename', '') or '').strip()
            or full_name
            or username
            or (getattr(profile, 'employee_code', '') or '').strip()
        )
        hname = (
            (getattr(employee_master, 'hindi_name', '') or '').strip()
            or (getattr(employee_obj, 'hname', '') or '').strip()
            or name
        )
        ip_number = (
            (getattr(profile, 'ip_number', '') or '').strip()
            or (getattr(employee_master, 'ip_number', '') or '').strip()
            or ''
        )
        empcode = (
            (getattr(profile, 'employee_code', '') or '').strip()
            or username
        )
        return {
            'name': name or empcode or '-',
            'hname': hname or name or empcode or '-',
            'ip': ip_number,
            'empcode': str(empcode or ''),
        }

    manager_data = []
    hod_profiles = UserProfile.objects.none()
    office_profiles = UserProfile.objects.none()
    if office_code:
        office_profiles = UserProfile.objects.filter(office_code=office_code).select_related('user', 'employee').distinct()
        hod_profiles = UserProfile.objects.filter(
            office_code=office_code,
        ).filter(
            Q(roles__name__iexact='hod') | Q(user__roles__name__iexact='hod'),
            approval_status='approved'
        ).select_related('user', 'employee').distinct()

        for hod_profile in hod_profiles:
            try:
                user_obj = getattr(hod_profile, 'user', None)
                hod_identity = _profile_identity(hod_profile)
                hod_display_name = hod_identity['name']

                employees_qs = UserProfile.objects.filter(
                    approval_status='approved',
                ).select_related('user', 'employee')

                match_keys = []
                if hod_profile.name:
                    match_keys.append(hod_profile.name)
                if hod_profile.hod_name:
                    match_keys.append(hod_profile.hod_name)
                if getattr(hod_profile, 'employee_code', None):
                    match_keys.append(str(hod_profile.employee_code))
                if user_obj and getattr(user_obj, 'username', None):
                    match_keys.append(user_obj.username)

                if match_keys:
                    q = Q()
                    for key in set(match_keys):
                        if key and str(key).strip():
                            q |= Q(hod_name__iexact=str(key).strip())
                    if q:
                        employees_qs = employees_qs.filter(q)

                emp_dicts = []
                for p in employees_qs:
                    try:
                        u = getattr(p, 'user', None)
                        uid = getattr(u, 'id', None)
                        if uid is None:
                            continue
                        employee_identity = _profile_identity(p)
                        emp_dicts.append({
                            'id': uid,
                            'name': employee_identity['name'],
                            'hname': employee_identity['hname'],
                            'empcode': employee_identity['empcode'],
                            'ip': employee_identity['ip'],
                        })
                    except Exception:
                        continue

                try:
                    hod_user_id = getattr(user_obj, 'id', None)
                    hod_entry = {
                        'id': hod_user_id,
                        'name': hod_identity['name'],
                        'hname': hod_identity['hname'],
                        'empcode': hod_identity['empcode'],
                        'ip': hod_identity['ip'],
                    }
                    emp_dicts = [e for e in emp_dicts if e.get('id') != hod_user_id]
                    emp_dicts.insert(0, hod_entry)
                except Exception:
                    pass

                manager_data.append({
                    'hod_name': hod_display_name,
                    'hod_hname': hod_identity['hname'],
                    'hod_id': getattr(user_obj, 'id', None),
                    'employees': emp_dicts,
                    'division_frozen': False,
                    'division_qpr_id': None,
                })
            except Exception:
                continue

    # Detect frozen division QPR per HOD and compute state totals (current quarter/year)
    try:
        hod_user_map = {}
        hod_user_ids = []
        for idx, entry in enumerate(manager_data):
            hid = entry.get('hod_id')
            if hid is not None:
                hod_user_map[hid] = idx
                hod_user_ids.append(hid)

        total_hods = len(hod_user_ids)

        state_totals = {k: 0 for k in NUMERIC_KEYS}
        frozen_count = 0
        for hid in hod_user_ids:
            hod_rec = QPRRecord.objects.filter(
                user_id=hid,
                is_quarterly_frozen=True,
                quarter=current_quarter,
                year=current_year
            ).first()

            if hod_rec and hod_rec.user:
                frozen_count += 1
                hod_office = getattr(getattr(hod_rec.user, 'profile', None), 'office_code', None)
                team_ids = list(UserProfile.objects.filter(office_code=hod_office).values_list('user_id', flat=True))
               
                # Log team diagnostic info
                logger.debug("HOD office found with team IDs")

                team_records = QPRRecord.objects.filter(
                    user_id__in=team_ids,
                    quarter=current_quarter,
                    year=current_year
                )

                # Log team records count
                logger.debug("Team records retrieved: %s", team_records.count())

                for rec in team_records:
                    d = serialize_qpr_record(rec)
                    for k in NUMERIC_KEYS:
                        v = d.get(k)
                        if v:
                            val = int(v)
                            state_totals[k] += val
                            if k == 's2_meetings':
                                logger.debug("Processing metric for user %s", rec.user_id)

                if hid in hod_user_map:
                    idx = hod_user_map[hid]
                    manager_data[idx]['division_frozen'] = True
                    manager_data[idx]['division_qpr_id'] = hod_rec.id
       
        try:
            mgr_qprs = ManagerQPR.objects.filter(quarter__in=_quarter_query_values(current_quarter), financial_year=current_year, user__profile__office_code=office_code)
            for mq in mgr_qprs:
                try:
                    mvals = _serialize_managerqpr(mq)
                    for k in NUMERIC_KEYS:
                        try:
                            v = int(mvals.get(k, 0) or 0)
                            state_totals[k] += v
                        except Exception:
                            continue
                except Exception:
                    continue

            adm_qprs = AdminQPR.objects.filter(quarter__in=_quarter_query_values(current_quarter), financial_year=current_year, user__profile__office_code=office_code)
            for aq in adm_qprs:
                try:
                    avals = _serialize_adminqpr(aq)
                    for k in NUMERIC_KEYS:
                        try:
                            v = int(avals.get(k, 0) or 0)
                            state_totals[k] += v
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass


    except Exception:
        state_totals = {k: 0 for k in NUMERIC_KEYS}
        frozen_count = 0
        total_hods = hod_profiles.count() if 'hod_profiles' in locals() else 0

    state_qpr = None
    state_qpr_items = []
    try:
        state_qpr = {'quarter': current_quarter, 'year': current_year, 'frequency': 'quarterly', 'officeName': 'State Aggregated', 'officeCode': ''}
        for k in NUMERIC_KEYS:
            state_qpr[k] = state_totals.get(k, 0)
            state_qpr_items.append((k, state_qpr[k]))
    except Exception:
        state_qpr = None
    report_query = urlencode({'quarter': current_quarter, 'year': current_year})

    return render(request, 'qpr/manager_report.html', {
        'manager_data': manager_data,
        'state_totals': state_totals,
        'state_qpr': state_qpr,
        'state_qpr_items': state_qpr_items,
        'frozen_count': frozen_count,
        'total_hods': total_hods,
        'quarter_filter': current_quarter,
        'year_filter': current_year,
        'quarter_options': _qpr_filter_quarter_options(),
        'year_options': _qpr_filter_year_options_for_users([up.user for up in office_profiles if getattr(up, 'user', None)]),
        'report_query': report_query,
        'current_lang': request.session.get('lang', 'en'),
    })


@login_required
def manager_state_qpr(request):
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    manager_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
    office_code = getattr(manager_profile, 'office_code', None)

    if not office_code:
        messages.error(request, 'Manager office not found')
        return redirect('manager_report')

    hod_profiles = UserProfile.objects.filter(office_code=office_code, roles__name__iexact='hod').select_related('user')
    hod_user_ids = [getattr(h.user, 'id', None) for h in hod_profiles if getattr(h.user, 'id', None) is not None]

    raw_quarter = (request.GET.get('quarter') or get_current_quarter()).strip()
    raw_year = (request.GET.get('year') or get_current_year_label()).strip()
    current_quarter = escape(raw_quarter)
    current_year = escape(raw_year)
    try:
        _quarter_label_to_daterange(current_quarter, current_year)
    except Exception:
        current_quarter = get_current_quarter()
        current_year = get_current_year_label()

    state_totals = {k: 0 for k in NUMERIC_KEYS}
    s9_sub_committees_total = 0
    s9_meetings_total = 0
    s9_agenda_any = False
    s9_dates = []
    s10_dates = []
    s12_1_texts = []
    s12_2_texts = []
    s12_3_texts = []
    if hod_user_ids:
        hod_qprs = QPRRecord.objects.filter(user_id__in=hod_user_ids, frequency__iexact='quarterly', is_quarterly_frozen=True, quarter=current_quarter, year=current_year)
        for rec in hod_qprs:
            try:
                d = serialize_qpr_record(rec)
            except Exception:
                continue
            for k in NUMERIC_KEYS:
                try:
                    v = d.get(k)
                    if v is None or v == '':
                        continue
                    state_totals[k] += int(v)
                except Exception:
                    continue
            try:
                sc = d.get('s9_sub_committees')
                if sc not in (None, ''):
                    try:
                        s9_sub_committees_total += int(sc)
                    except Exception:
                        pass
                sm = d.get('s9_meetings_count')
                if sm not in (None, ''):
                    try:
                        s9_meetings_total += int(sm)
                    except Exception:
                        pass
                agenda = d.get('s9_agenda_hindi')
                if agenda not in (None, ''):
                    if str(agenda).strip().lower() in ('yes','y','true','1','हाँ','हां'):
                        s9_agenda_any = True
                if d.get('s9_date'):
                    s9_dates.append(str(d.get('s9_date')))
                if d.get('s10_date'):
                    s10_dates.append(str(d.get('s10_date')))
                if d.get('s12_1'):
                    s12_1_texts.append(str(d.get('s12_1')).strip())
                if d.get('s12_2'):
                    s12_2_texts.append(str(d.get('s12_2')).strip())
                if d.get('s12_3'):
                    s12_3_texts.append(str(d.get('s12_3')).strip())
            except Exception:
                pass
    try:
        mgr_qprs = ManagerQPR.objects.filter(quarter__in=_quarter_query_values(current_quarter), financial_year=current_year, user__profile__office_code=office_code)
        for mq in mgr_qprs:
            try:
                mvals = _serialize_managerqpr(mq)
                for k in NUMERIC_KEYS:
                    try:
                        state_totals[k] += int(mvals.get(k, 0) or 0)
                    except Exception:
                        continue
            except Exception:
                continue
            try:
                sc = getattr(mq, 's9_sub_committees', None) or getattr(mq, 's9_sub_committees_count', None)
                if sc not in (None, ''):
                    try:
                        s9_sub_committees_total += int(sc)
                    except Exception:
                        pass
                sm = getattr(mq, 's9_meetings_count', None) or getattr(mq, 's9_meetings_organized', None)
                if sm not in (None, ''):
                    try:
                        s9_meetings_total += int(sm)
                    except Exception:
                        pass
                agenda = getattr(mq, 's9_agenda_hindi', None)
                if agenda not in (None, ''):
                    if str(agenda).strip().lower() in ('yes','y','true','1','हाँ','हां'):
                        s9_agenda_any = True
                if getattr(mq, 's9_meeting_date', None):
                    s9_dates.append(str(getattr(mq, 's9_meeting_date')))
                if getattr(mq, 's10_meeting_date', None):
                    s10_dates.append(str(getattr(mq, 's10_meeting_date')))
                if getattr(mq, 's11_innovative_work', None):
                    s12_1_texts.append(str(getattr(mq, 's11_innovative_work')).strip())
                if getattr(mq, 's11_special_events', None):
                    s12_2_texts.append(str(getattr(mq, 's11_special_events')).strip())
                if getattr(mq, 's11_hindi_medium_works', None):
                    s12_3_texts.append(str(getattr(mq, 's11_hindi_medium_works')).strip())
            except Exception:
                pass

        adm_qprs = AdminQPR.objects.filter(quarter__in=_quarter_query_values(current_quarter), financial_year=current_year, user__profile__office_code=office_code)
        for aq in adm_qprs:
            try:
                avals = _serialize_adminqpr(aq)
                for k in NUMERIC_KEYS:
                    try:
                        state_totals[k] += int(avals.get(k, 0) or 0)
                    except Exception:
                        continue
            except Exception:
                continue
            try:
                sc = getattr(aq, 'a_s9_sub_committees', None) or getattr(aq, 's9_sub_committees', None)
                if sc not in (None, ''):
                    try:
                        s9_sub_committees_total += int(sc)
                    except Exception:
                        pass
                sm = getattr(aq, 'a_s9_meetings_count', None) or getattr(aq, 's9_meetings_count', None) or getattr(aq, 'a_s9_meetings_organized', None)
                if sm not in (None, ''):
                    try:
                        s9_meetings_total += int(sm)
                    except Exception:
                        pass
                agenda = getattr(aq, 'a_s9_agenda_hindi', None) or getattr(aq, 's9_agenda_hindi', None)
                if agenda not in (None, ''):
                    if str(agenda).strip().lower() in ('yes','y','true','1','हाँ','हां'):
                        s9_agenda_any = True
                if getattr(aq, 'a_s9_date', None) or getattr(aq, 's9_date', None) or getattr(aq, 'a_s9_meeting_date', None):
                    s9_dates.append(str(getattr(aq, 'a_s9_date', None) or getattr(aq, 's9_date', None) or getattr(aq, 'a_s9_meeting_date', None)))
                if getattr(aq, 'a_s10_date', None) or getattr(aq, 's10_date', None) or getattr(aq, 'a_s10_meeting_date', None):
                    s10_dates.append(str(getattr(aq, 'a_s10_date', None) or getattr(aq, 's10_date', None) or getattr(aq, 'a_s10_meeting_date', None)))
                if getattr(aq, 'a_s11_innovative_work', None) or getattr(aq, 's11_innovative_work', None):
                    s12_1_texts.append(str(getattr(aq, 'a_s11_innovative_work', None) or getattr(aq, 's11_innovative_work', None)).strip())
                if getattr(aq, 'a_s11_special_events', None) or getattr(aq, 's11_special_events', None):
                    s12_2_texts.append(str(getattr(aq, 'a_s11_special_events', None) or getattr(aq, 's11_special_events', None)).strip())
                if getattr(aq, 'a_s11_hindi_medium_works', None) or getattr(aq, 's11_hindi_medium_works', None):
                    s12_3_texts.append(str(getattr(aq, 'a_s11_hindi_medium_works', None) or getattr(aq, 's11_hindi_medium_works', None)).strip())
            except Exception:
                pass
    except Exception:
        pass

    state_qpr = {
        'quarter': current_quarter,
        'year': current_year,
        'frequency': 'quarterly',
        'officeName': 'State Aggregated',
        'officeCode': '',
    }
    for k in NUMERIC_KEYS:
        state_qpr[k] = state_totals.get(k, 0)

    state_qpr['s9_sub_committees'] = s9_sub_committees_total or 0
    state_qpr['s9_meetings_count'] = s9_meetings_total or 0
    state_qpr['s9_agenda_hindi'] = 'Yes' if s9_agenda_any else 'No'
    state_qpr['s9_date'] = s9_dates[0] if s9_dates else ''
    state_qpr['s10_date'] = s10_dates[0] if s10_dates else ''
    state_qpr['s12_1'] = ' | '.join([t for t in s12_1_texts if t]) if s12_1_texts else ''
    state_qpr['s12_2'] = ' | '.join([t for t in s12_2_texts if t]) if s12_2_texts else ''
    state_qpr['s12_3'] = ' | '.join([t for t in s12_3_texts if t]) if s12_3_texts else ''

    return render(request, 'qpr/report_detail.html', {
        'initial_qpr_json': state_qpr,
    })


@login_required
def manager_report_detail(request, year, quarter):
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    manager_office = getattr(request.user.profile, 'office_code', None)
    if not manager_office:
        first = QPRRecord.objects.filter(user=request.user).first()
        manager_office = first.officeCode if first else None

    if not manager_office:
        return redirect('manager_report')

    users_qs = UserProfile.objects.filter(office_code=manager_office).filter(
        Q(roles__name='user') | Q(user__roles__name='user')
    ).select_related('user').distinct().order_by('hod_name', 'name')
    total_users = users_qs.count()
    normalized_year = year
    submitted = QPRRecord.objects.filter(officeCode=manager_office, year=normalized_year, quarter=quarter, is_submitted=True)
    submitted_users_count = submitted.values('user').distinct().count()
    total_users = users_qs.count()
    all_submitted = submitted_users_count >= total_users
    grouped = {}
    submitted_map = {r.user.id: r for r in submitted if r.user is not None}

    for up in users_qs:
        user = up.user
        rec = submitted_map.get(getattr(user, 'id', None))
        hod = up.hod_name or 'Unassigned'
        if hod not in grouped:
            grouped[hod] = []
        employee_code = str(up.employee_code or '').strip()
        emp_obj = getattr(up, 'employee', None)
        if emp_obj is None and employee_code:
            try:
                emp_obj = Employee.objects.filter(empcode=int(employee_code)).first()
            except (TypeError, ValueError):
                emp_obj = None

        master_employee = None
        if employee_code:
            try:
                master_employee = EmployeeMaster.objects.filter(empcode=int(employee_code), is_active=True).first()
            except (TypeError, ValueError):
                master_employee = None

        profile_name = (up.name or '').strip()
        if profile_name == employee_code:
            profile_name = ''

        employee_name = (
           
            (getattr(master_employee, 'name', '') or '').strip()
            or (getattr(emp_obj, 'ename', '') or '').strip()
            or profile_name
            or getattr(user, 'username', '')
        )
        try:
            emp_hname = ''
           
            if emp_obj is not None:
                emp_hname = getattr(emp_obj, 'hname', '') or ''
        except Exception:
            emp_hname = ''

        grouped[hod].append({
            'name': employee_name,
            'hname': emp_hname or employee_name,
            'empcode': employee_code,
            'email': up.email or '',
            'submitted': bool(rec),
            'submitted_at': rec.updated_at if rec else None,
            'qpr_record_id': rec.id if rec else None,
        })

    context = {
        'year': year if year else '2025-2026',
        'quarter': quarter,
        'office_code': manager_office,
        'grouped': grouped,
        'all_submitted': all_submitted,
        'submitted_users_count': submitted_users_count,
        'total_users': total_users,
        'current_lang': request.session.get('lang', 'en'),
    }
   
    return render(request, 'qpr/manager_report_detail.html', context)

@login_required
def qpr_certificate(request, record_id):
    try:
        rec = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    mgr_office = getattr(request.user.profile, 'office_code', None)
    if user_role(request.user) == 'manager' and mgr_office and mgr_office != rec.officeCode:
        return redirect('manager_report')

    context = {
        'record': rec,
    }
    return render(request, 'qpr/certificate.html', context)


@login_required
def manager_report_detail_by_record(request, record_id):
    try:
        rec = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')
   
    safe_year = rec.year if rec.year else '2025-2026'
    return manager_report_detail(request, safe_year, rec.quarter)


@login_required
def certificate_form_view(request, record_id):
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    CertificateData.objects.get_or_create(
        qpr_record=record,
        defaults={
            'financial_year': record.year if record.year else '2025-2026',
            'quarter_ending': record.quarter if record.quarter else '',
        }
    )
    return redirect('certificate_part2_list')

@login_required
def certificate_display_view(request, record_id):
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    cert_data = CertificateData.objects.filter(qpr_record=record).first()
    if not cert_data:
        return redirect('certificate_form', record_id=record.id)

    context = {
        'record': record,
        'cert_data': cert_data,
    }
    return render(request, 'qpr/certificate_display.html', context)


def _certificate_year_options():
    today = timezone.localdate()
    fiscal_year_start = today.year if today.month >= 4 else today.year - 1
    return [f"{year}-{year + 1}" for year in range(2024, fiscal_year_start + 1)]


@login_required
def manager_certificate_list(request):
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')

    certificates = ManagerCertificate.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'qpr/manager_certificate_list.html', {
        'certificates': certificates,
        'current_lang': request.session.get('lang', 'en'),
    })


@login_required
def manager_certificate_new(request):
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')

    if request.method == 'POST':
        quarter = request.POST.get('quarter', '').strip()
        year = request.POST.get('year', '').strip()
        if not quarter or not year:
            messages.error(request, 'Quarter and Year are required.')
            return redirect('manager_certificate_new')

        manager_profile = getattr(request.user, 'userprofile', None) or getattr(request.user, 'profile', None)
        office_code = getattr(manager_profile, 'office_code', '') or ''
        certificate, _ = ManagerCertificate.objects.get_or_create(
            user=request.user,
            quarter=quarter,
            year=year,
            defaults={
                'financial_year': year,
                'office_code': office_code,
            }
        )
        if certificate.is_submitted:
            return redirect('manager_certificate_view', pk=certificate.id)
        return redirect('manager_certificate_form', pk=certificate.id)

    return render(request, 'qpr/manager_certificate_select_quarter.html', {
        'quarters': ['Q1', 'Q2', 'Q3', 'Q4'],
        'years': _certificate_year_options(),
        'current_lang': request.session.get('lang', 'en'),
    })


@login_required
def manager_certificate_form(request, pk):
    """Fill and submit standalone manager certificate details."""
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')

    certificate = get_object_or_404(ManagerCertificate, pk=pk, user=request.user)
    if certificate.is_submitted:
        return redirect('manager_certificate_view', pk=certificate.id)

    if request.method == 'POST':
        certificate.chairperson_name = request.POST.get('chairperson_name', '').strip()
        certificate.chairperson_designation = request.POST.get('chairperson_designation', '').strip()
        certificate.organization_name = request.POST.get('organization_name', '').strip()
        certificate.phone_fax = request.POST.get('phone_fax', '').strip()
        certificate.email = request.POST.get('email', '').strip()
        certificate.place = request.POST.get('place', '').strip()
        certificate_date = request.POST.get('certificate_date', '').strip()
        certificate.certificate_date = certificate_date or None
        certificate.is_submitted = True
        certificate.submitted_at = timezone.now()
        certificate.save()
        messages.success(request, 'Certificate submitted.')
        return redirect('manager_certificate_view', pk=certificate.id)

    return render(request, 'qpr/manager_certificate_form.html', {
        'certificate': certificate,
        'current_lang': request.session.get('lang', 'en'),
    })


@login_required
def manager_certificate_view(request, pk):
    """View standalone manager certificate."""
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')

    certificate = get_object_or_404(ManagerCertificate, pk=pk, user=request.user)
    return render(request, 'qpr/certificate.html', {
        'manager_certificate': certificate,
        'current_lang': request.session.get('lang', 'en'),
    })


@login_required
def manager_certificate_print(request, pk):
    return manager_certificate_view(request, pk)


@login_required
def manager_certificate_delete(request, pk):
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')
    if request.method != 'POST':
        return redirect('manager_certificate_list')
    certificate = get_object_or_404(ManagerCertificate, pk=pk, user=request.user)
    certificate.delete()
    messages.success(request, 'Certificate deleted.')
    return redirect('manager_certificate_list')



@login_required
def certificate_part2_list(request):
    lang = request.session.get('lang', 'en')
   
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')
   
    certificates = QPRPartTwo.objects.filter(user=request.user).order_by('-created_at')
   
    context = {
        'certificates': certificates,
        'current_lang': lang
    }
    return render(request, 'qpr/certificate_part2_list.html', context)


@login_required
def certificate_part2_new(request):
    lang = request.session.get('lang', 'en')
   
    if not user_has_role(request.user, 'manager'):
        return HttpResponseForbidden('Only managers can access certificates.')
   
    if request.method == 'POST':
        quarter = request.POST.get('quarter', '').strip()
        year = request.POST.get('year', '').strip()
       
        if not quarter or not year:
            messages.error(request, 'Quarter and Year are required.')
            return redirect('certificate_part2_list')
       
        existing = QPRPartTwo.objects.filter(
            user=request.user,
            quarter=quarter,
            year=year
        ).first()
       
        if existing:
            return redirect('certificate_part2_edit', pk=existing.id)
       
        certificate = QPRPartTwo.objects.create(
            user=request.user,
            quarter=quarter,
            year=year,
            financial_year=year
        )

        OfficersWorkInHindi.objects.create(
            report=certificate,
            level='ds_and_above',
            total_officers=0,
            knowledge_of_hindi=0,
            not_doing=0,
            doing_upto_25=0,
            doing_26_to_50=0,
            doing_51_to_75=0,
            doing_more_76=0,
            doing_cent_percent=0
        )
        OfficersWorkInHindi.objects.create(
            report=certificate,
            level='below_ds',
            total_officers=0,
            knowledge_of_hindi=0,
            not_doing=0,
            doing_upto_25=0,
            doing_26_to_50=0,
            doing_51_to_75=0,
            doing_more_76=0,
            doing_cent_percent=0
        )
       
        return redirect('certificate_part2_form', pk=certificate.id)
   
    quarters = ['Q1', 'Q2', 'Q3', 'Q4']
    today = timezone.localdate()
    fiscal_year_start = today.year if today.month >= 4 else today.year - 1
    years = [f"{year}-{year + 1}" for year in range(2024, fiscal_year_start + 1)]
   
    context = {
        'quarters': quarters,
        'years': years,
        'current_lang': lang
    }
    return render(request, 'qpr/certificate_part2_select_quarter.html', context)


def _part2_related_context(certificate):
    staff_data = {
        item.category: item
        for item in certificate.staff_knowledge.all()
    }
    typing_data = {
        item.category: item
        for item in certificate.typing_knowledge.all()
    }
    codes_data = {
        item.category: item
        for item in certificate.codes_manuals.all()
    }
    translation_data = {}
    for item in certificate.translation_knowledge.all():
        key = 'yet' if item.category == 'yet_to_be_trained' else item.category
        translation_data[key] = {
            'officers': item.officers_count,
            'employees': item.employees_count,
            'total': item.total_count,
        }

    return {
        'staff_data': staff_data,
        'typing_data': typing_data,
        'translation_data': translation_data,
        'codes_data': codes_data,
    }


@login_required
@require_http_methods(["GET", "POST"])
def certificate_part2_form(request, pk):
    lang = request.session.get('lang', 'en')
    # Harden: reject GET requests that attempt to include form submission parameters in the query string
    if request.method == 'GET':
        forbidden_keys = {'quarter', 'year', 'total_sub_offices', 'is_notified_rule_10_4'}
        if any(k in request.GET for k in forbidden_keys):
            return HttpResponseNotAllowed(['POST'], "Form submission parameters are not allowed in a GET query string.")
    try:
        certificate = QPRPartTwo.objects.get(pk=pk, user=request.user)
    except QPRPartTwo.DoesNotExist:
        messages.error(request, 'Certificate not found.')
        return redirect('certificate_part2_list')
   
    if certificate.user != request.user:
        return HttpResponseForbidden('You cannot edit this certificate.')
   
    OfficersWorkInHindi.objects.get_or_create(
        report=certificate,
        level='ds_and_above',
        defaults={
            'total_officers': 0,
            'knowledge_of_hindi': 0,
            'not_doing': 0,
            'doing_upto_25': 0,
            'doing_26_to_50': 0,
            'doing_51_to_75': 0,
            'doing_more_76': 0,
            'doing_cent_percent': 0
        }
    )
    OfficersWorkInHindi.objects.get_or_create(
        report=certificate,
        level='below_ds',
        defaults={
            'total_officers': 0,
            'knowledge_of_hindi': 0,
            'not_doing': 0,
            'doing_upto_25': 0,
            'doing_26_to_50': 0,
            'doing_51_to_75': 0,
            'doing_more_76': 0,
            'doing_cent_percent': 0
        }
    )
   
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
       
        certificate.is_notified_rule_10_4 = request.POST.get('is_notified_rule_10_4') == 'true'
        certificate.total_sub_offices = int(request.POST.get('total_sub_offices', 0) or 0)
        certificate.notified_sub_offices = int(request.POST.get('notified_sub_offices', 0) or 0)
        certificate.computer_training_total_staff = int(request.POST.get('computer_training_total_staff', 0) or 0)
        certificate.computer_training_trained = int(request.POST.get('computer_training_trained', 0) or 0)
        certificate.computer_training_working = int(request.POST.get('computer_training_working', 0) or 0)
        certificate.total_computers = int(request.POST.get('total_computers', 0) or 0)
        certificate.hindi_enabled_computers = int(request.POST.get('hindi_enabled_computers', 0) or 0)
        certificate.hindi_work_percentage = float(request.POST.get('hindi_work_percentage', 0) or 0)
        certificate.officials_issued_rule_8_4_orders = int(request.POST.get('officials_issued_rule_8_4_orders', 0) or 0)
        certificate.training_total_duration_hours = int(request.POST.get('training_total_duration_hours', 0) or 0)
        certificate.training_imparted_hindi = int(request.POST.get('training_imparted_hindi', 0) or 0)
        certificate.training_imparted_english = int(request.POST.get('training_imparted_english', 0) or 0)
        certificate.training_imparted_mixed = int(request.POST.get('training_imparted_mixed', 0) or 0)
        certificate.sec8_total_sections = int(request.POST.get('sec8_total_sections', 0) or 0)
        certificate.sec8_inspected_sections = int(request.POST.get('sec8_inspected_sections', 0) or 0)
        certificate.sec8_total_sub_offices = int(request.POST.get('sec8_total_sub_offices', 0) or 0)
        certificate.sec8_inspected_sub_offices = int(request.POST.get('sec8_inspected_sub_offices', 0) or 0)
        certificate.magazines_total = int(request.POST.get('magazines_total', 0) or 0)
        certificate.magazines_hindi = int(request.POST.get('magazines_hindi', 0) or 0)
        certificate.magazines_english = int(request.POST.get('magazines_english', 0) or 0)
        certificate.expenditure_total_books = float(request.POST.get('expenditure_total_books', 0) or 0)
        certificate.expenditure_hindi_books = float(request.POST.get('expenditure_hindi_books', 0) or 0)
       
        hindi_event_start = request.POST.get('hindi_event_start_date')
        if hindi_event_start:
            certificate.hindi_event_start_date = hindi_event_start
        hindi_event_end = request.POST.get('hindi_event_end_date')
        if hindi_event_end:
            certificate.hindi_event_end_date = hindi_event_end
        seminar_date = request.POST.get('seminar_date')
        if seminar_date:
            certificate.seminar_date = seminar_date
       
        certificate.seminar_subject = request.POST.get('seminar_subject', '')
       
        other_act_date = request.POST.get('other_activities_date')
        if other_act_date:
            certificate.other_activities_date = other_act_date
        certificate.other_activities_subject = request.POST.get('other_activities_subject', '')
   
        certificate.chairperson_name = request.POST.get('chairperson_name', '')
        certificate.chairperson_designation = request.POST.get('chairperson_designation', '')
        certificate.chairperson_phone = request.POST.get('chairperson_phone', '')
        certificate.chairperson_fax = request.POST.get('chairperson_fax', '')
        certificate.chairperson_email = request.POST.get('chairperson_email', '')

        categories = ['stenographer', 'typist_clerk', 'tax_postal']

        for cat in categories:
            TypingStenographyKnowledge.objects.update_or_create(
        report=certificate,
        category=cat,
        defaults={
            'total_no': int(request.POST.get(f'typing_total_{cat}', 0) or 0),
            'trained_in_hindi': int(request.POST.get(f'typing_trained_{cat}', 0) or 0),
            'work_in_hindi': int(request.POST.get(f'typing_working_{cat}', 0) or 0),
            'yet_to_be_trained': int(request.POST.get(f'typing_yet_{cat}', 0) or 0),
            }
        )

        TranslationKnowledge.objects.update_or_create(
            report=certificate,
            category='engaged',
            defaults={
                'officers_count': int(request.POST.get('translation_officers_engaged', 0) or 0),
                'employees_count': int(request.POST.get('translation_employees_engaged', 0) or 0),
                'total_count': int(request.POST.get('translation_total_engaged', 0) or 0),
                }
            )

        TranslationKnowledge.objects.update_or_create(
            report=certificate,
            category='trained',
            defaults={
                'officers_count': int(request.POST.get('translation_officers_trained', 0) or 0),
                'employees_count': int(request.POST.get('translation_employees_trained', 0) or 0),
                'total_count': int(request.POST.get('translation_total_trained', 0) or 0),
                }
            )

        TranslationKnowledge.objects.update_or_create(
            report=certificate,
            category='yet_to_be_trained',
            defaults={
            'officers_count': int(request.POST.get('translation_officers_yet', 0) or 0),
            'employees_count': int(request.POST.get('translation_employees_yet', 0) or 0),
            'total_count': int(request.POST.get('translation_total_yet', 0) or 0),
                }
            )

        StaffHindiKnowledge.objects.update_or_create(
            report=certificate,
            category='total',
            defaults={
            'officers_total': int(request.POST.get('staff_total_officers', 0) or 0),
            'employees_total': int(request.POST.get('staff_total_employees', 0) or 0),
            'total_count': int(request.POST.get('staff_total_total', 0) or 0),
            }
        )

        StaffHindiKnowledge.objects.update_or_create(
            report=certificate,
            category='secretarial',
            defaults={
                'officers_total': int(request.POST.get('staff_secretarial_officers', 0) or 0),
                'employees_total': int(request.POST.get('staff_secretarial_employees', 0) or 0),
                'total_count': int(request.POST.get('staff_secretarial_total', 0) or 0),
                }
        )

        StaffHindiKnowledge.objects.update_or_create(
            report=certificate,
            category='knowledge',
            defaults={
                'officers_working': int(request.POST.get('staff_knowledge_officers_working', 0) or 0),
                'officers_proficient': int(request.POST.get('staff_knowledge_officers_proficient', 0) or 0),
                'employees_working': int(request.POST.get('staff_knowledge_employees_working', 0) or 0),
                'employees_proficient': int(request.POST.get('staff_knowledge_employees_proficient', 0) or 0),
                'total_count': int(request.POST.get('staff_knowledge_total', 0) or 0),
            }
        )

        StaffHindiKnowledge.objects.update_or_create(
            report=certificate,
            category='being_trained',
            defaults={
                'officers_total': int(request.POST.get('staff_trained_officers', 0) or 0),
                'employees_total': int(request.POST.get('staff_trained_employees', 0) or 0),
                'total_count': int(request.POST.get('staff_trained_total', 0) or 0),
            }
        )

        StaffHindiKnowledge.objects.update_or_create(
            report=certificate,
            category='yet_to_be_trained',
            defaults={
                'officers_total': int(request.POST.get('staff_yet_officers', 0) or 0),
                'employees_total': int(request.POST.get('staff_yet_employees', 0) or 0),
                'total_count': int(request.POST.get('staff_yet_total', 0) or 0),
            }
        )

        CodeManualStandardForms.objects.update_or_create(
            report=certificate,
            category='acts_rules',
            defaults={
            'total_no': int(request.POST.get('codes_total_acts_rules', 0) or 0),
            'bilingual_no': int(request.POST.get('codes_bilingual_acts_rules', 0) or 0),
            }
        )

        CodeManualStandardForms.objects.update_or_create(
            report=certificate,
            category='standard_forms',
            defaults={
            'total_no': int(request.POST.get('codes_total_standard_forms', 0) or 0),
            'bilingual_no': int(request.POST.get('codes_bilingual_standard_forms', 0) or 0),
            }
        )

        post_names = request.POST.getlist('section13_post_name')
        hq_sanctioned_list = request.POST.getlist('section13_hq_sanctioned')
        hq_vacant_list = request.POST.getlist('section13_hq_vacant')
        sub_sanctioned_list = request.POST.getlist('section13_sub_sanctioned')
        sub_vacant_list = request.POST.getlist('section13_sub_vacant')
        certificate.hindi_posts.all().delete()

        for i in range(len(post_names)):
            if post_names[i]:
                HindiPost.objects.create(
                    report=certificate,
                    designation=post_names[i],
                    hq_sanctioned=int(hq_sanctioned_list[i] or 0),
                    hq_vacant=int(hq_vacant_list[i] or 0),
                    sub_sanctioned=int(sub_sanctioned_list[i] or 0),
                    sub_vacant=int(sub_vacant_list[i] or 0)
                )

        urls = request.POST.getlist('section14_url')
        website_indexes = request.POST.getlist('section14_index')

        certificate.websites.all().delete()

        for i, url in enumerate(urls):
            if url:
                row_index = website_indexes[i] if i < len(website_indexes) else str(i + 1)
                status_key = f'section14_status_{row_index}'
                option_key = f'section14_option_{row_index}'
                status = request.POST.get(status_key, '')
                WebsiteDetail.objects.create(
                    report=certificate,
                    url=url,
                    status=status,
                    has_language_option=option_key in request.POST
                )
       
        OfficersWorkInHindi.objects.update_or_create(
            report=certificate,
            level='ds_and_above',
            defaults={
                'total_officers': int(request.POST.get('sec11_total', 0) or 0),
                'knowledge_of_hindi': int(request.POST.get('sec11_knowledge', 0) or 0),
                'not_doing': int(request.POST.get('sec11_not_doing', 0) or 0),
                'doing_upto_25': int(request.POST.get('sec11_0_25', 0) or 0),
                'doing_26_to_50': int(request.POST.get('sec11_26_50', 0) or 0),
                'doing_51_to_75': int(request.POST.get('sec11_51_75', 0) or 0),
                'doing_more_76': int(request.POST.get('sec11_76_99', 0) or 0),
                'doing_cent_percent': int(request.POST.get('sec11_100', 0) or 0),
            }
        )

        OfficersWorkInHindi.objects.update_or_create(
            report=certificate,
            level='below_ds',
            defaults={
                'total_officers': int(request.POST.get('sec12_total', 0) or 0),
                'knowledge_of_hindi': int(request.POST.get('sec12_knowledge', 0) or 0),
                'not_doing': int(request.POST.get('sec12_not_doing', 0) or 0),
                'doing_upto_25': int(request.POST.get('sec12_0_25', 0) or 0),
                'doing_26_to_50': int(request.POST.get('sec12_26_50', 0) or 0),
                'doing_51_to_75': int(request.POST.get('sec12_51_75', 0) or 0),
                'doing_more_76': int(request.POST.get('sec12_76_99', 0) or 0),
                'doing_cent_percent': int(request.POST.get('sec12_100', 0) or 0),
            }
        )

        if action == 'submit':
            if not certificate.quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
                messages.error(request, 'Invalid quarter.')
                return render(request, 'qpr/certificate_part2_form.html', {
                    'part2': certificate,
                    'quarter': certificate.quarter,
                    'year': certificate.year,
                    'current_lang': lang,
                    **_part2_related_context(certificate),
                })
           
            certificate.is_submitted = True
            certificate.submitted_by = request.user
            certificate.submitted_at = timezone.now()
            certificate.save()
           
            messages.success(request, translate_text('Certificate submitted successfully!', lang))
            return redirect('certificate_part2_list')
        else:
            certificate.save()
            messages.success(request, translate_text('Certificate saved as draft.', lang))
            return redirect('certificate_part2_form', pk=certificate.id)
   
    context = {
        'part2': certificate,
        'quarter': certificate.quarter,
        'year': certificate.year,
        'current_lang': lang,
        **_part2_related_context(certificate),
    }
    return render(request, 'qpr/certificate_part2_form.html', context)


@login_required
def certificate_part2_edit(request, pk):
    return certificate_part2_form(request, pk)


@login_required
def certificate_part2_view(request, pk):
    lang = request.session.get('lang', 'en')
   
    try:
        certificate = QPRPartTwo.objects.get(pk=pk, user=request.user)
    except QPRPartTwo.DoesNotExist:
        messages.error(request, 'Certificate not found.')
        return redirect('certificate_part2_list')
   
    context = {
        'certificate': certificate,
        'part2': certificate,
        'quarter': certificate.quarter,
        'year': certificate.year,
        'current_lang': lang,
        'readonly': True,
        **_part2_related_context(certificate),
    }
    return render(request, 'qpr/certificate_part2_form.html', context)


@login_required
def certificate_part2_print(request, pk):
    lang = request.session.get('lang', 'en')
   
    try:
        certificate = QPRPartTwo.objects.get(pk=pk, user=request.user)
    except QPRPartTwo.DoesNotExist:
        messages.error(request, 'Certificate not found.')
        return redirect('certificate_part2_list')
 
    office_name = ""
    try:
        user_profile = request.user.profile
        office_name = user_profile.office_name if hasattr(user_profile, 'office_name') else ""
    except:
        pass
   
    context = {
        'certificate': certificate,
        'office_name': office_name,
        'part2': certificate,
        'current_lang': lang
    }
    return render(request, 'qpr/certificate_part2_comprehensive_print.html', context)

@require_POST
@login_required
def certificate_part2_delete(request, pk):
    lang = request.session.get('lang', 'en')
   
    try:
        certificate = QPRPartTwo.objects.get(pk=pk, user=request.user)
    except QPRPartTwo.DoesNotExist:
        messages.error(request, 'Certificate not found.')
        return redirect('certificate_part2_list')
   
    if certificate.is_submitted:
        messages.error(request, 'Submitted certificates cannot be deleted.')
        return redirect('certificate_part2_list')
   
    # At this point request.method is guaranteed to be POST due to @require_POST
    certificate.delete()
    messages.success(request, translate_text('Certificate deleted.', lang))
   
    return redirect('certificate_part2_list')
    
@login_required
def process_user_approval(request, profile_id, action):
    if not user_has_role(request.user, ['hod', 'admin']):
        messages.error(request, "Unauthorized action.")
        return redirect('dashboard')

    target_profile = get_object_or_404(UserProfile, id=profile_id)
    is_admin = user_has_role(request.user, 'admin')
    is_hod = user_has_role(request.user, 'hod')
    redirect_name = 'dashboard' if is_admin else 'qpr_hod_dashboard'
    
    if action not in {'approve', 'reject'}:
        messages.error(request, "Invalid approval action.")
        return redirect(redirect_name)
    
    can_process = False
    if is_admin and target_profile.approval_status == 'pending_admin':
        admin_state = getattr(getattr(request.user, 'profile', None), 'office_state', None)
        can_process = (
            (target_profile.hod_name or '').strip().upper() == 'ADMIN'
            and bool(admin_state)
            and (target_profile.office_state or '').strip().lower() == str(admin_state).strip().lower()
        )
    
    if not can_process and is_hod and target_profile.approval_status == 'pending':
        hod_profile = getattr(request.user, 'profile', None)
        hod_identifiers = {
            str(value).strip().lower()
            for value in [
                getattr(hod_profile, 'hod_name', None),
                getattr(hod_profile, 'name', None),
                getattr(hod_profile, 'employee_code', None),
                getattr(request.user, 'username', None),
            ]
            if value
        }
        can_process = (target_profile.hod_name or '').strip().lower() in hod_identifiers
    
    if not can_process:
        messages.error(request, "You are not authorized to process this approval request.")
        return redirect(redirect_name)
   
    if action == 'approve':
        master_record = Employee.objects.filter(empcode=target_profile.employee_code).first()
       
        if master_record:
            target_profile.name = master_record.ename
            target_user = target_profile.user
            target_user.first_name = master_record.ename
            target_user.save()
       
        target_profile.approval_status = 'approved'
        target_profile.save()
       
        #send_system_email(target_profile.user, request, 'accepted_alert')
        messages.success(request, f"User {target_profile.employee_code} approved.")
       
    elif action == 'reject':
        target_profile.approval_status = 'rejected'
        target_profile.save()
        #send_system_email(target_profile.user, request, 'rejected_alert')
        messages.warning(request, f"User {target_profile.employee_code} rejected.")

    return redirect(redirect_name) 
@login_required
def backup_user_dashboard(request):
    context = {
        'role': 'backup_user', 
        'current_lang': request.session.get('lang', 'en'),
        'user': request.user
    }
    return render(request, 'dashboard.html', context)
