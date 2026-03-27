import os,io,csv,random,hashlib,json
from .utils import load_employee_data
from datetime import datetime
from datetime import timedelta
from urllib import request
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Count, Min
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout, get_user_model
from django.http import FileResponse
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from django.core.cache import cache
from weasyprint import HTML
from pypdf import PdfWriter, PdfReader
from django.template.loader import render_to_string
import tempfile
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
    Employee, CustomUser, Role, DataAccessLog, ArchivedUser, cipher_suite,
    Office,
    QPRRecord, Section1FilesData, Section2MeetingsData,
    Section3OfficialLanguagesData, Section4HindiLettersData,
    Section5EnglishRepliedHindiData, Section6IssuedLettersData,
    Section7NotingsData, Section8WorkshopsData,
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData,
    Section11SpecificAchievementsData, UserProfile, ManagerRequest, EditRequest,
    TypingUsageReport, CertificateData
    , QPRPartTwo, StaffHindiKnowledge, HindiPost
)
from .forms import CustomLoginForm, CustomUserCreationForm, TypingUsageReportForm, CertificateDataForm
from .employeeform import EmployeeForm
from .serializers import EmployeeSerializer
from .utils import send_system_email, get_allowed_quarters
from typing import cast
from datetime import date
from .templatetags.translate_tags import translate_text
from .minio_service import get_all_events
FONT_PATH = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'NIRMALA.TTF')
pdfmetrics.registerFont(TTFont('HindiFont', FONT_PATH))
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from .minio_service import get_all_events, upload_event, delete_event
from .minio_service import upload_event, upload_images_to_existing_event, delete_event
from .utils import load_employee_data
from .utils import ensure_current_financial_year
from .models import FinancialYear
from django.http import JsonResponse
import csv
import hashlib
import io
import json
import os
import random
import tempfile
from datetime import date, datetime, timedelta
from typing import cast
from urllib import request

# Third-party / Django Imports
from captcha.models import CaptchaStore, logger
from deep_translator import GoogleTranslator
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, logout
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Min, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from gtts import gTTS
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from weasyprint import HTML

# Local App Imports
from .employeeform import EmployeeForm
from .forms import (
    CertificateDataForm, CustomLoginForm, 
    CustomUserCreationForm, TypingUsageReportForm
)
from .minio_service import (
    delete_event, get_all_events, 
    upload_event, upload_images_to_existing_event
)
from .models import (
    ArchivedUser, CertificateData, CustomUser, DataAccessLog, 
    EditRequest, Employee, HindiPost, ManagerRequest, Office, 
    QPRPartTwo, QPRRecord, Role, Section1FilesData, Section2MeetingsData, 
    Section3OfficialLanguagesData, Section4HindiLettersData, 
    Section5EnglishRepliedHindiData, Section6IssuedLettersData, 
    Section7NotingsData, Section8WorkshopsData, 
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData, 
    Section11SpecificAchievementsData, StaffHindiKnowledge, 
    TypingUsageReport, UserProfile, cipher_suite
)
from .serializers import EmployeeSerializer
from .templatetags.translate_tags import translate_text
from .utils import get_allowed_quarters, load_employee_data, send_system_email
from .signals import User

def api_get_employee_details(request):
    emp_code = request.GET.get('empcode', '').strip()

    if not emp_code:
        return JsonResponse({
            "status": "error",
            "message": "Empcode required"
        })

    # 🔥 LOAD EXCEL DATA
    EMPLOYEE_DATA = load_employee_data()

    # # 🔥 DEBUG (temporary)
    # print("Searching emp_code:", emp_code)
    # print("Available keys sample:", list(EMPLOYEE_DATA.keys())[:10])

    if emp_code not in EMPLOYEE_DATA:
        return JsonResponse({
            "status": "error",
            "message": "Invalid Employee Code"
        })

    data = EMPLOYEE_DATA[emp_code]

    return JsonResponse({
        "status": "success",
        "name": data.get("name"),
        "hindi_name": data.get("hindi_name"),
        "mobile": data.get("mobile"),
        "designation": data.get("designation")
    })
@staff_member_required
def admin_events_dashboard(request):

    events = get_all_events()

    return render(request, "admin_events_dashboard.html", {
        "events": events
    })


@staff_member_required

def admin_upload_event(request):

    folder = request.GET.get("folder")

    if request.method == "POST":

        event_date = request.POST.get("event_date")
        event_name = request.POST.get("event_name")
        images = request.FILES.getlist("images")

        try:

            if folder:
                upload_images_to_existing_event(folder, images)

            else:
                upload_event(event_date, event_name, images)

            return JsonResponse({"status": "success"})

        except Exception as e:

            return JsonResponse({
                "status": "error",
                "message": str(e)
            })

    return render(request,"admin_upload_event.html",{
        "folder":folder
    })

@staff_member_required
def admin_delete_event(request, folder):
    try:
        delete_event(folder)
        messages.success(request, "Event deleted successfully")
    except Exception as e:
        messages.error(request, f"Failed to delete event: {e}")

    return redirect("admin_events_dashboard")


# Helper functions to safely access a user's roles for type-checkers
def user_has_role(user, role_name):
    """Check if user has a specific role
    Can accept either a single role string or a list of role strings"""
    if user is None or not user.is_authenticated:
        return False
    
    profile = getattr(user, 'profile', None)
    if isinstance(role_name, list):
        user_has = user.roles.filter(name__in=role_name).exists()
        profile_has = profile.roles.filter(name__in=role_name).exists() if profile else False
        return user_has or profile_has
    else:
        user_has = user.roles.filter(name=role_name).exists()
        profile_has = profile.roles.filter(name=role_name).exists() if profile else False
        return user_has or profile_has

def user_role(user):
    """Return user's primary role (for backward compatibility)
    Returns the first role from: admin > manager > hod > user > None"""
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


@staff_member_required
def admin_events_dashboard(request):

    events = get_all_events()

    return render(request, "admin_events_dashboard.html", {
        "events": events
    })


@staff_member_required

def admin_upload_event(request):

    folder = request.GET.get("folder")

    if request.method == "POST":

        event_date = request.POST.get("event_date")
        event_name = request.POST.get("event_name")
        images = request.FILES.getlist("images")

        try:

            if folder:
                upload_images_to_existing_event(folder, images)

            else:
                upload_event(event_date, event_name, images)

            return JsonResponse({"status": "success"})

        except Exception as e:

            return JsonResponse({
                "status": "error",
                "message": str(e)
            })

    return render(request,"admin_upload_event.html",{
        "folder":folder
    })


@staff_member_required
def admin_delete_event(request, folder):
    try:
        delete_event(folder)
        messages.success(request, "Event deleted successfully")
    except Exception as e:
        messages.error(request, f"Failed to delete event: {e}")
    return redirect("admin_events_dashboard")

def user_get_all_roles(user):
    """Get all role names as a list"""
    if user is None or not user.is_authenticated:
        return []
    profile = getattr(user, 'profile', None)
    user_roles = set(user.roles.values_list('name', flat=True))
    profile_roles = set(profile.roles.values_list('name', flat=True)) if profile else set()
    return list(sorted(user_roles.union(profile_roles)))

def is_admin(user):
    """Check if user is an admin"""
    return user.is_authenticated and user_has_role(user, 'admin')

def can_access_user_site(user):
    """User site accessible to all authenticated users (everyone starts as 'user')"""
    return user.is_authenticated and user_has_role(user, 'user')

def can_access_hod_site(user):
    """HOD site accessible to users with 'hod' role"""
    return user.is_authenticated and user_has_role(user, 'hod')

def can_access_manager_site(user):
    """Manager site accessible to users with 'manager' role"""
    return user.is_authenticated and user_has_role(user, 'manager')

def get_active_hods(office_code=None):
    """Get list of valid HODs only"""
    
    hod_query = UserProfile.objects.filter(
        roles__name='hod',
        approval_status='approved'
    )

    # If office_code is provided, filter by it
    # If office_code is None/empty, show HODs with no office_code restriction or all HODs
    if office_code:
        hod_query = hod_query.filter(office_code=office_code)

    return list(
        hod_query.values_list('hod_name', flat=True).distinct()
    )

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
    # Financial year runs from Apr 1 -> Mar 31. If current month is April or later,
    # the fiscal year starts this calendar year; otherwise it started last calendar year.
    if today.month >= 4:
        start = today.year
    else:
        start = today.year - 1
    return f"{start}-{start+1}"


def get_quarter_end_dates():
    """
    Returns a dictionary with quarter end dates for current and upcoming quarters.
    {
        'current': date of quarterend for current quarter,
        'next': date of quarter end for next quarter
    }
    """
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

def _quarter_label_to_daterange(quarter_label, year_label):
    """Return (start_date, end_date) for given quarter label and fiscal year label like '2025-2026'"""
    try:
        base = get_base_year(year_label)
    except Exception:
        base = date.today().year
    q = (quarter_label or '').strip()
    # Apr-Jun
    if 'Jun' in q or 'जून' in q:
        start = date(base, 4, 1)
        end = date(base, 6, 30)
    # Jul-Sep
    elif 'Sep' in q or 'सितंबर' in q or 'सित' in q:
        start = date(base, 7, 1)
        end = date(base, 9, 30)
    # Oct-Dec
    elif 'Dec' in q or 'दिसंबर' in q or 'दिस' in q:
        start = date(base, 10, 1)
        end = date(base, 12, 31)
    # Jan-Mar
    else:
        # This quarter belongs to next calendar year
        start = date(base+1, 1, 1)
        end = date(base+1, 3, 31)
    return (start, end)

NUMERIC_KEYS = [
    's1_total','s1_hindi','s2_meetings','s2_minutes','s2_papers_total','s2_papers_hindi',
    's3_total','s3_bilingual','s3_english','s3_hindi_only',
    's4_total','s4_no_reply','s4_replied_hindi','s4_replied_eng',
    's5_total','s5_hindi','s5_english','s5_noreply',
    's6_a_hindi','s6_a_eng','s6_a_total','s6_b_hindi','s6_b_eng','s6_b_total','s6_c_hindi','s6_c_eng','s6_c_total',
    's7_hindi','s7_eng','s7_total','s7_eoffice',
    's8_workshops','s8_officers','s8_employees'
]

def _aggregate_records_for_range(user, start_dt, end_dt, source_frequency='daily'):
    """Sum numeric fields of submitted records for a user whose period overlaps [start_dt,end_dt].

    Only records matching `source_frequency` are considered. Records without explicit
    period_start/period_end are ignored (no fallback to quarter) to avoid accidental
    full-quarter overlaps.
    """
    total = {k: 0 for k in NUMERIC_KEYS}
    if not start_dt or not end_dt:
        return total

    # Base queryset: filter by user, submission state and frequency only.
    # We intentionally avoid requiring explicit period_start/period_end here so
    # older records that may miss one of those fields are still considered.
    qs = QPRRecord.objects.filter(
        user=user,
        is_submitted=True,
        frequency__iexact=(source_frequency or '')
    )

    for r in qs:
        # Determine effective start/end for the record with safe fallbacks.
        try:
            r_start = getattr(r, 'period_start', None)
            r_end = getattr(r, 'period_end', None)

            # If one of the explicit bounds is missing, try to infer sensibly
            # without modifying the DB. These heuristics keep behaviour non-destructive.
            if r_start and not r_end:
                freq = (getattr(r, 'frequency', '') or '').lower()
                if freq == 'daily':
                    r_end = r_start
                elif freq == 'weekly':
                    r_end = r_start + timedelta(days=5)
                elif freq == 'monthly':
                    # last day of month for r_start
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

            # As a last resort use created_at date if neither bound exists
            if not r_start and not r_end:
                created = getattr(r, 'created_at', None)
                if created:
                    r_start = created.date()
                    r_end = r_start
                else:
                    # Skip records with no usable date info
                    continue

            # Now check overlap with requested range
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


def _get_quarter_range_for_date(dt):
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


def determine_submission_frequency(user, submission_date=None, is_submitted=True):
    """Enforce submission rules and return (frequency, period_start, period_end).

    Rules implemented:
    - Normal operation: `daily` submissions allowed on each working day (Mon-Sat).
    - If a user has at least one `daily` in the current week but has missed earlier working day(s) up to today,
      the server will require a single `weekly` submission for that week (Mon-Sat). After a weekly is created,
      further `daily` submissions for that week are blocked.
    - If a user has zero `daily` submissions for the entire current week, they are blocked from daily/weekly
      submissions until month end; on month end they may submit a single `monthly` for that month.
    - If a user has zero `daily` submissions for the entire month, they are blocked from daily/weekly/monthly
      until quarter end; on quarter end they may submit a single `quarterly` for that quarter.

    If `is_submitted` is False (saving as Draft), this function will return `daily` for drafts and not enforce blocks.
    Raises ValueError with a descriptive message when submission is not allowed at this time.
    """
    if submission_date is None:
        submission_date = date.today()

    # Week (Mon-Sat) starting Monday
    week_start = submission_date - timedelta(days=submission_date.weekday())
    week_end = week_start + timedelta(days=5)  # Mon-Sat (Saturday is week end)

    # Month range
    month_start = date(submission_date.year, submission_date.month, 1)
    if submission_date.month == 12:
        month_end = date(submission_date.year, 12, 31)
    else:
        month_end = date(submission_date.year, submission_date.month + 1, 1) - timedelta(days=1)

    # Quarter range
    q_start, q_end = _get_quarter_range_for_date(submission_date)

    def _last_working_before(d):
        while d.weekday() > 5:  # Sunday (6)
            d = d - timedelta(days=1)
        return d

    month_last_working = _last_working_before(month_end)
    quarter_last_working = _last_working_before(q_end)

    # Drafts are given a neutral daily default without enforcement
    if not is_submitted:
        return ('daily', submission_date, submission_date)


def compute_period(frequency, selected_date=None, quarter=None, year=None):
    """Compute (period_start, period_end) for given frequency.

    - frequency: 'daily'|'weekly'|'monthly'|'quarterly'
    - selected_date: datetime.date used for daily/weekly/monthly
    - quarter, year: used for quarterly
    """
    if selected_date is None:
        selected_date = timezone.localdate()

    if frequency == 'daily':
        return (selected_date, selected_date)

    if frequency == 'weekly':
        # Week is Mon-Sat (server convention)
        start = selected_date - timedelta(days=selected_date.weekday())
        end = start + timedelta(days=5)
        # Clamp within quarter boundaries to avoid crossing into adjacent quarters
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
        # Clamp within quarter boundaries to avoid spanning adjacent quarters
        try:
            q_start, q_end = _get_quarter_range_for_date(selected_date)
            if start < q_start: start = q_start
            if end > q_end: end = q_end
        except Exception:
            pass
        return (start, end)

    if frequency == 'quarterly':
        # Use existing helper to map quarter label + fiscal year to range
        if quarter and year:
            try:
                return _quarter_label_to_daterange(quarter, year)
            except Exception:
                pass
        # fallback: compute quarter containing selected_date
        return _get_quarter_range_for_date(selected_date)

    # default fallback
    return (selected_date, selected_date)


def is_period_overlapping(user, start, end, exclude_id=None):
    """Return True if any submitted QPRRecord for user overlaps [start,end]."""
    if not start or not end:
        return False
    qs = QPRRecord.objects.filter(user=user, is_submitted=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.filter(period_start__lte=end, period_end__gte=start).exists()


def _allowed_frequencies_for_date(user, selected_date):
    """Return a dict with allowed frequencies and missing days for the selected_date.

    Result example:
    {
      'allowed': ['daily','weekly'],
      'missing_days_week': ['2026-03-23','2026-03-24'],
      'missing_days_month': [...],
      'min_date': '2025-04-01', 'max_date': '2026-04-25'
    }
    """
    today = timezone.localdate()
    # min_date: earliest submitted period_start for user or start of current financial year
    earliest = QPRRecord.objects.filter(user=user).order_by('period_start').first()
    if earliest and earliest.period_start:
        min_date = earliest.period_start
    else:
        # fiscal year start: Apr 1 of current fiscal year
        fy_start = today.year if today.month >= 4 else today.year - 1
        min_date = date(fy_start, 4, 1)

    # Max date: one month ahead from today (user can plan one month in advance)
    try:
        # Handle month overflow (e.g., Jan 31 -> Feb doesn't have 31 days)
        if today.month == 12:
            next_month_year, next_month_month = today.year + 1, 1
        else:
            next_month_year, next_month_month = today.year, today.month + 1
        
        # Try to create the same day in next month; fallback to last day of month if it doesn't exist
        try:
            max_date = date(next_month_year, next_month_month, today.day)
        except ValueError:
            # Day doesn't exist in target month (e.g., Jan 31 -> Feb 31 doesn't exist)
            # Use last day of the month
            if next_month_month == 2:
                max_date = date(next_month_year, 2, 29 if next_month_year % 4 == 0 else 28)
            elif next_month_month in [4, 6, 9, 11]:
                max_date = date(next_month_year, next_month_month, 30)
            else:
                max_date = date(next_month_year, next_month_month, 31)
    except Exception:
        # Fallback to today + 30 days if anything fails
        max_date = today + timedelta(days=30)

    # Normalize selected_date within bounds
    if selected_date < min_date:
        selected_date = min_date
    if selected_date > max_date:
        selected_date = max_date

    # Week (Mon-Sat)
    q_start, q_end = _get_quarter_range_for_date(selected_date)

    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=5)

    # CLIP TO QUARTER
    week_start = max(week_start, q_start)
    week_end = min(week_end, q_end)
    week_days = [
    d for d in (week_start + timedelta(days=i) for i in range((week_end - week_start).days + 1))
    if d.weekday() <= 5 and q_start <= d <= q_end ]
    # Submitted daily dates in week
    submitted_week = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(week_start, week_end)).values_list('period_start', flat=True))
    missing_week = [d for d in week_days if d not in submitted_week and d >= min_date and d <= max_date]

    # Month
    month_start = date(selected_date.year, selected_date.month, 1)
    if selected_date.month == 12:
        month_end = date(selected_date.year, 12, 31)
    else:
        month_end = date(selected_date.year, selected_date.month + 1, 1) - timedelta(days=1)
    month_days = [month_start + timedelta(days=i) for i in range((month_end - month_start).days + 1) if (month_start + timedelta(days=i)).weekday() <= 5]
    submitted_month = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(month_start, month_end)).values_list('period_start', flat=True))
    missing_month = [d for d in month_days if d not in submitted_month and d >= min_date and d <= max_date]

    # Quarter
    q_start, q_end = _get_quarter_range_for_date(selected_date)
    quarter_days = [q_start + timedelta(days=i) for i in range((q_end - q_start).days + 1) if (q_start + timedelta(days=i)).weekday() <= 5]
    submitted_quarter = set(QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(q_start, q_end)).values_list('period_start', flat=True))
    missing_quarter = [d for d in quarter_days if d not in submitted_quarter and d >= min_date and d <= max_date]

    allowed = ['daily']
    
    # Helper to find last working day before a date
    def _last_working_before(d):
        while d.weekday() > 5:  # Sunday is 6
            d = d - timedelta(days=1)
        return d
    
    month_last = _last_working_before(month_end)
    quarter_last = _last_working_before(q_end)
    
    # weekly allowed if there are missing working days in the week
    if len(missing_week) > 0:
        allowed.append('weekly')
    # monthly allowed only at month end if there are missing working days in the month
    if len(missing_month) > 0 and selected_date >= month_last:
        allowed.append('monthly')
    # quarterly allowed only at quarter end if there are missing working days in the quarter
    if len(missing_quarter) > 0 and selected_date >= quarter_last:
        allowed.append('quarterly')

    return {
        'allowed': allowed,
        'missing_week': [d.isoformat() for d in missing_week],
        'missing_month': [d.isoformat() for d in missing_month],
        'missing_quarter': [d.isoformat() for d in missing_quarter],
        'min_date': min_date.isoformat(),
        'max_date': max_date.isoformat(),
        'default_date': timezone.localdate().isoformat()
    }


@login_required
def api_qpr_availability(request):
    """Return allowed frequencies and missing days for a given date."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    d = request.GET.get('date')
    try:
        sel = datetime.strptime(d, '%Y-%m-%d').date() if d else timezone.localdate()
    except Exception:
        return JsonResponse({'error': 'Invalid date param'}, status=400)
    data = _allowed_frequencies_for_date(request.user, sel)
    return JsonResponse(data)


def compute_cumulative_for_record(record):
    """Return dict with daily/weekly/monthly/quarterly aggregates for the given record."""
    user = record.user
    # determine quarter range first (always parse from record's quarter/year)
    q_start, q_end = None, None
    try:
        q_start, q_end = _quarter_label_to_daterange(record.quarter, record.year or '')
    except Exception:
        # fallback to today's month
        today = date.today()
        q_start = date(today.year, today.month, 1)
        if today.month == 12:
            q_end = date(today.year, 12, 31)
        else:
            q_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    
    # determine base date for daily aggregation
    base = None
    if getattr(record, 'period_start', None):
        base = record.period_start
    elif getattr(record, 'period_end', None):
        base = record.period_end
    else:
        # If period is missing, try to infer from record.frequency and created_at
        freq = (getattr(record, 'frequency', '') or '').lower()
        created = getattr(record, 'created_at', None)
        if freq == 'weekly' and created:
            base = created.date()
        elif freq == 'monthly' and created:
            base = created.date()
        elif freq == 'daily' and created:
            base = created.date()
        else:
            # use quarter end as fallback base for daily/weekly/monthly when no specific period
            base = q_end
    
    # daily
    day_start = base
    day_end = base
    # weekly (Mon-Sat week used elsewhere; keep to Mon-Sat)
    week_start = day_start - timedelta(days=day_start.weekday())
    week_end = week_start + timedelta(days=5)
    # monthly
    month_start = date(day_start.year, day_start.month, 1)
    # compute month end
    if day_start.month == 12:
        month_end = date(day_start.year, 12, 31)
    else:
        month_end = date(day_start.year, day_start.month + 1, 1) - timedelta(days=1)

    # Helper to try preferred source then fall back to lower-frequency sources
    def _aggregate_with_fallback(user, start_dt, end_dt, preferred):
        order = []
        pref = (preferred or '').lower()
        if pref == 'daily':
            order = ['daily']
        elif pref == 'weekly':
            order = ['weekly', 'daily']
        elif pref == 'monthly':
            order = ['monthly', 'weekly', 'daily']
        else:
            # quarterly or unknown: try monthly -> weekly -> daily
            order = ['monthly', 'weekly', 'daily']

        last_totals = None
        for src in order:
            try:
                totals = _aggregate_records_for_range(user, start_dt, end_dt, source_frequency=src)
            except Exception:
                totals = {k: 0 for k in NUMERIC_KEYS}
            last_totals = totals
            # if any numeric key is non-zero, accept these totals
            if any((totals.get(k, 0) or 0) != 0 for k in NUMERIC_KEYS):
                return totals
        # if all zero, return the last computed (likely zeros)
        return last_totals or {k: 0 for k in NUMERIC_KEYS}

    try:
        daily_tot = _aggregate_with_fallback(user, day_start, day_end, 'daily')
        weekly_tot = _aggregate_with_fallback(user, week_start, week_end, 'weekly')
        monthly_tot = _aggregate_with_fallback(user, month_start, month_end, 'monthly')
        quarterly_tot = _aggregate_with_fallback(user, q_start, q_end, 'quarterly')
        return {
            'daily': daily_tot,
            'weekly': weekly_tot,
            'monthly': monthly_tot,
            'quarterly': quarterly_tot,
        }
    except Exception:
        zeros = {k: 0 for k in NUMERIC_KEYS}
        return {'daily': zeros.copy(), 'weekly': zeros.copy(), 'monthly': zeros.copy(), 'quarterly': zeros.copy()}

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
    # Include submission frequency and explicit period when available
    data['frequency'] = getattr(record, 'frequency', 'quarterly') if record else 'quarterly'
    data['period_start'] = getattr(record, 'period_start', None)
    data['period_end'] = getattr(record, 'period_end', None)
    data['is_quarterly_frozen'] = getattr(record, 'is_quarterly_frozen', False)
    # Normalize numeric keys: convert None/empty to 0 so cumulative sums include them
    try:
        for k in NUMERIC_KEYS:
            if data.get(k) is None or data.get(k) == '':
                data[k] = 0
    except Exception:
        pass
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
    events = get_all_events()
    return render(request, "home.html", {"events": events})

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
    """Central Dashboard Router - Routes each role to their dedicated dashboard"""
    user = request.user
    role = request.session.get('active_role', user_role(user))
    profile = getattr(user, 'profile', None)
    
    # Dashboard routing uses session active_role (set at login) or falls back to user's primary role
    
    context = {
        'current_lang': request.session.get('lang', 'en'),
        'role': role
    }
    if role == 'user' and profile:
        if profile.approval_status == 'pending':
            if profile.hod_name =="ADMIN":
                messages.warning(request, "Your registration is pending Admin approval.")
            else:    
                messages.warning(request, "Your registration is pending HOD approval. You may edit your details while you wait.")
            return redirect('qpr_user_profile') # Locks them into the profile edit page
        elif profile.approval_status == 'rejected':
            messages.error(request, "Your registration was rejected. Please verify your details and update them, or contact admin.")
            return redirect('qpr_user_profile')
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
        user = cast(CustomUser, form.get_user())
        auth_login(self.request, user)
        current_lang = self.request.session.get('lang', 'en')
        
        # Get the selected role from the form
        selected_role = form.cleaned_data.get('role')
        # Check if user actually has the selected role and use it; otherwise fall back
        if selected_role and user_has_role(user, selected_role):
            active_role = selected_role
        else:
            active_role = user_role(user)

        # Set session variables and ensure session is saved
        self.request.session['lang'] = current_lang
        self.request.session['active_role'] = active_role
        self.request.session.modified = True
        self.request.session.save()
        
        send_system_email(user, self.request, 'login')
        # If user is a regular user and hasn't completed profile, force profile completion first
        try:
            profile = getattr(user, 'profile', None)
        except Exception:
            profile = None

        if user_role(user) == 'user' and profile and not profile.profile_updated:
            return redirect('qpr_user_profile')

        return redirect(self.get_success_url())

    def form_invalid(self, form):
        username = form.data.get('username')
        user = CustomUser.objects.filter(username=username).first()
        # Ensure we have a password string before passing to check_password
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

            # hod_name removed from user-editable form (admin-managed)
            employee_code = request.POST.get('employee_code', '').strip()
            phone = request.POST.get('phone', '').strip()

            # Generate OTP and keep signup data in session until verification
            otp = str(random.randint(100000, 999999))
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
                            defaults={"employee_code": user.username}
                        )
                        profile.approval_status = 'pending'
                        profile.profile_updated = False
                        profile.save()
                        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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
            if user.otp_created_at and (timezone.now() - user.otp_created_at).total_seconds() < 300:
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
    if getattr(user_to_archive, 'id', None) == getattr(request.user, 'id', None):
        messages.error(request, "You cannot archive yourself.")
        return redirect('dashboard')

    # 3. Create Snapshot for Archive
    # Employee.empcode is an IntegerField. Try to resolve a numeric empcode
    # from the user's username or from their profile.employee_code.
    empcode_val = None
    # Prefer profile.employee_code if available
    profile = getattr(user_to_archive, 'profile', None)
    if profile and getattr(profile, 'employee_code', None):
        try:
            empcode_val = int(profile.employee_code)
        except (TypeError, ValueError):
            empcode_val = None

    # Fallback: try to use username if it's numeric
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

    # 4. Create Archive Record
    ArchivedUser.objects.create(
        username=user_to_archive.username,
        email_hash=user_to_archive.email_hash,
        encrypted_email_data=user_to_archive.encrypted_email_data,
        original_user_id=user_to_archive.pk,
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
    """Unified profile view - Employee form with strict validation, HOD approval workflow, and controlled editing"""

    lang = request.session.get('lang', 'en')
    user = request.user
    profile = getattr(user, 'profile', None)

    from .models import Employee, Office, EditRequest
    from .employeeform import EmployeeForm

    employee = None

    # ===============================
    # 🔐 EDIT REQUESTS & PERMISSIONS
    # ===============================
    approved_request = EditRequest.objects.filter(
        user=user,
        request_type='profile',
        status='approved'
    ).first()

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

    # HEAD-style permission (lenient but controlled)
    can_edit = (not user.is_frozen) or user.is_edit_allowed or (approved_request is not None)

    # ===============================
    # 📩 POST LOGIC
    # ===============================
    if request.method == 'POST':

        # 🔒 Strict lock
        if not can_edit:
            messages.error(
                request,
                translate_text("Your profile is locked. Request edit permission.", lang),
                extra_tags='danger'
            )
            return redirect('dashboard')

        EMPLOYEE_DATA = load_employee_data()

        empcode = request.POST.get('empcode', '').strip()
        username = request.POST.get('username', '').strip().upper()
        phone = request.POST.get('phone', '').strip()

        # ❌ Validate empcode
        if empcode not in EMPLOYEE_DATA:
            messages.error(request, "Invalid Employee Code")
            return redirect('profile')

        employee_data = EMPLOYEE_DATA[empcode]

        # ❌ Validate name
        if username != employee_data["name"]:
            messages.error(request, "Name does not match official records")
            return redirect('profile')

        # ❌ Validate phone
        if phone != employee_data["mobile"]:
            messages.error(request, "Mobile number does not match official records")
            return redirect('profile')

        # Fetch employee after validation
        employee = Employee.objects.filter(empcode=empcode).first()

        # 🔥 HOD mandatory
        hod_name_post = request.POST.get('hod_name', '').strip()
        if not hod_name_post:
            messages.error(request, "HOD/Approver selection is required")
            return redirect('profile')

        # Email validation
        new_email = request.POST.get('email', '').lower().strip()

        if not new_email:
            messages.error(
                request,
                translate_text("Email is required.", lang),
                extra_tags='danger'
            )
            return redirect('profile')

        email_hash = hashlib.sha256(new_email.encode()).hexdigest()

        if CustomUser.objects.filter(email_hash=email_hash).exclude(pk=user.pk).exists():
            messages.error(
                request,
                translate_text("Email already in use.", lang),
                extra_tags='danger'
            )
            return redirect('profile')

        # ===============================
        # ✅ SAVE USER
        # ===============================
        user.set_email(new_email)
        user.is_edit_allowed = False
        user.save()

        # ===============================
        # ✅ SAVE PROFILE
        # ===============================
        if profile:
            profile.employee_code = empcode
            profile.phone = phone
            profile.office_code = request.POST.get('office_code', '').strip()
            profile.office_name = request.POST.get('office_name', '').strip()
            profile.email = new_email
            profile.hod_name = hod_name_post

            # 🔒 Approval workflow
            profile.profile_updated = True
            profile.approval_status = "pending_admin" if hod_name_post == "ADMIN" else "pending"

            profile.save()

        # ===============================
        # ✅ EMPLOYEE FORM
        # ===============================
        form = EmployeeForm(request.POST, instance=employee)

        if form.is_valid():
            emp_instance = form.save(commit=False)

            exams = request.POST.getlist("hindi_exam")
            emp_instance.highest_exam = ",".join(exams)

            emp_instance.empcode = empcode
            emp_instance.save()
        else:
            messages.error(request, "Please fill all required Employee details correctly.")
            return redirect('profile')

        # ===============================
        # 🔄 CLEANUP
        # ===============================
        if approved_request:
            approved_request.status = 'used'
            approved_request.save()

        send_system_email(user, request, 'update')

        messages.success(
            request,
            translate_text("Profile submitted successfully! Awaiting approval.", lang)
        )

        return redirect('dashboard')

    # ===============================
    # 📄 GET LOGIC
    # ===============================
    else:
        form = EmployeeForm(instance=employee)

    # ===============================
    # 📦 CONTEXT
    # ===============================
    offices = Office.objects.all()

    context = {
        'form': form,
        'employee': employee,
        'profile': profile,
        'qpr_office_name': profile.office_name if profile else '',
        'qpr_office_code': profile.office_code if profile else '',
        'qpr_phone': profile.phone if profile else '',
        'qpr_email': profile.email if profile else '',

        'available_hods': get_active_hods(profile.office_code) if profile else [],
        'current_hod': profile.hod_name if profile else None,

        'can_edit': can_edit,
        'offices': offices,

        'profile_updated': profile.profile_updated if profile else False,

        'approved_edit_request': approved_request,
        'pending_edit_request': pending_edit_request,
        'rejected_edit_request': rejected_edit_request,
    }

    return render(request, 'profile.html', context)
'''
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
        # Collect posted values
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        office_code = request.POST.get('office_code', '').strip()
        # Phone may be submitted by the user; ensure it's defined before use
        phone = request.POST.get('phone', '').strip()
        # Basic validation (HOD is admin-managed; do not require it from the user)
        if not username:
            messages.error(request, translate_text('Username is required', lang))
        elif User.objects.exclude(id=getattr(request.user, 'id', None)).filter(username=username).exists():
            messages.error(request, translate_text('Username already taken', lang))
        elif not email:
            messages.error(request, translate_text('Email is required', lang))
        elif not office_code:
            messages.error(request, translate_text('Office selection is required', lang))
        elif profile_submitted and not approved_edit_request:
            messages.error(request, translate_text('You cannot edit a submitted profile. Please request approval from Admin first.', lang))
        else:
            # Lookup office name
            from .models import Office
            office = Office.objects.filter(code=office_code).first()
            office_name = office.name if office else ''

            # Save profile and user (do not change hod_name here)
            profile.email = email
            profile.phone = phone or profile.phone
            profile.office_code = office_code
            profile.office_name = office_name
            profile.profile_updated = True
            profile.save()

            request.user.email = email
            # update username if changed
            if request.user.username != username:
                request.user.username = username
            request.user.save()

            # Clear approved request after edit
            if approved_edit_request:
                approved_edit_request.delete()

            messages.success(request, translate_text('Profile updated successfully! Your profile is now frozen. To edit it again, request approval from admin.', lang))
            return redirect('qpr_user_dashboard')

    # Get list of available HODs for selection
    available_hods = get_active_hods(profile.office_code) if profile.office_code else []
    # Get list of offices for dropdown
    from .models import Office
    offices = Office.objects.all()

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
        'offices': offices,
    }
    response = render(request, 'profile.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response'''

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
            admin = CustomUser.objects.filter(roles__name='admin').first()
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
        defaults={"employee_code": f"EMP{getattr(request.user, 'id', '')}"}
    )
    profile.refresh_from_db()
    # If profile not completed, redirect user to fill profile first (only first time)
    if not profile.profile_updated:
        return redirect('qpr_user_profile')
    qpr_records = QPRRecord.objects.filter(user=request.user)
    submitted_qprs = qpr_records.filter(is_submitted=True).count()
    
    # Get list of available HODs for dropdown
    available_hods = get_active_hods(profile.office_code)
    
    # Check if user has HOD or Manager roles (disable HOD selection if they do)
    is_hod_or_manager = user_has_role(request.user, ['hod', 'manager'])
    
    context = {
        'role': 'user',  # Explicitly set role for template to avoid showing other roles' content
        'profile': profile,
        'profile_status': 'Updated' if profile.profile_updated else 'Needs Update',
        'qpr_submitted': submitted_qprs > 0, 
        'qpr_count': qpr_records.count(),
        'user': request.user,
        'available_hods': available_hods,
        'current_hod': profile.hod_name or '',
        'is_hod_or_manager': is_hod_or_manager
    }
    response = render(request, 'dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response 
@login_required
def qpr_hod_dashboard(request):
    """HOD Dashboard - Department overview and employee statistics"""
    if not user_has_role(request.user, 'hod'): return redirect('/')
    lang = request.session.get('lang', 'en')
    
    # Force fresh database fetch
    from django.db import connections
    connections.close_all()
    
    current_quarter = get_current_quarter()
    current_year = get_current_year_label()

    hod_profile = UserProfile.objects.select_related('user').get(user=request.user)
    hod_name = hod_profile.hod_name or hod_profile.name
    hod_name = hod_name.strip() if hod_name else None
    
    from django.db.models import Q
    
    if hod_name:
        user_role_q = Q(roles__name='user') | Q(user__roles__name='user')
        users_under_hod = UserProfile.objects.filter(
            (user_role_q & Q(hod_name__iexact=hod_name)) | Q(user=request.user)
        ).distinct()
    else:
        users_under_hod = UserProfile.objects.filter(user=request.user).distinct()

    total_users = users_under_hod.count()
    qpr_submitted_count = 0
    profile_updated_count = users_under_hod.filter(profile_updated=True).count()

    for up in users_under_hod:

        current_qpr = up.user.qpr_records.filter(
        quarter=current_quarter,
        year=current_year
        ).first()
    if current_qpr and current_qpr.is_submitted:
        qpr_submitted_count += 1
    qpr_pending = total_users - qpr_submitted_count
    pending_approvals = users_under_hod.filter(approval_status='pending')
    context = {
        'role': 'hod',
        'total_users': total_users,
        'qpr_submitted': qpr_submitted_count,
        'qpr_pending': qpr_pending,
        'profile_updated': profile_updated_count,
        'hod_name': hod_name,
        'current_lang': lang,
        'current_quarter': current_quarter,
        'current_year': current_year,
        'pending_approvals': pending_approvals,
    }
    response = render(request, 'qpr/hod_dashboard.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response 

@login_required
def manager_dashboard(request):
    """Manager Dashboard - Manage system access and employee records"""
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')
    
    manager_office = getattr(request.user.profile, 'office_code', None)

    users = CustomUser.objects.select_related('profile').filter(profile__office_code=manager_office).order_by('-date_joined')

    # Get employee codes from users in this office
    office_employee_codes = CustomUser.objects.filter(profile__office_code=manager_office).values_list('profile__employee_code', flat=True)
    office_employee_codes = [str(code).zfill(3) if code else None for code in office_employee_codes if code]

    # Fetch employee records directly by empcode (which matches username/employee_code)
    raw_employees = Employee.objects.filter(empcode__in=office_employee_codes).order_by('-lastupdate')
    
    employee_data = []
    
    for emp in raw_employees:
        # Get the user by employee_code (which is the empcode)
        user = CustomUser.objects.filter(profile__employee_code=emp.empcode).first()

        # --- QPR DATA ---
        qpr_status_text = "Not Started"
        qpr_is_submitted = False
        latest_qpr_id = None
        qpr_last_updated = None
        
        # Get ID safely
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

    # Pending profile edit requests targeted to this manager
    pending_profile_requests = ManagerRequest.objects.filter(hod=request.user, request_type='profile', status='pending')
    
    # QPR edit requests (pending and approved) from employees in this manager's office
    manager_office = getattr(request.user.profile, 'office_code', None)
    pending_qpr_edits = []
    edit_requests_by_user = {}  # Map user_id -> EditRequest for quick lookup (pending or approved)
    
    if manager_office:
        # Get both pending and approved edit requests
        edit_requests = EditRequest.objects.filter(
            request_type='qpr',
            status__in=['pending', 'approved']  # Include both pending and approved
        ).select_related('user').filter(
            user__profile__office_code=manager_office
        )
        
        # Filter pending ones for the quick actions section
        pending_qpr_edits = [req for req in edit_requests if req.status == 'pending']
        
        # Build dictionary for template lookup (stores latest edit request per user)
        for req in edit_requests:
            # Only store if newer or first one
            if req.user_id not in edit_requests_by_user or req.created_at > edit_requests_by_user[req.user_id].created_at:
                edit_requests_by_user[req.user_id] = req
    
    # Enrich employee_data with edit request info
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
        'employees': employee_data,
        'pending_profile_requests': pending_profile_requests,
        'pending_qpr_edits': pending_qpr_edits,
    }
    return render(request, 'manager_dashboard.html', context)
@login_required
def admin_dashboard(request):
    if user_role(request.user) != 'admin': return redirect('/')
    
    # --- ACTIVE USERS ---
    users = CustomUser.objects.filter(is_active=True, is_archived=False).order_by('-date_joined')
    
    # --- ARCHIVED USERS ---
    archived_users = ArchivedUser.objects.all().order_by('-archived_at')

    current_quarter = get_current_quarter()
    current_year = get_current_year_label()
    
    hod_stats = []
    hods = UserProfile.objects.filter(roles__name='hod').order_by('name')
    for hod_profile in hods:
        hod_key = hod_profile.hod_name or hod_profile.name or hod_profile.employee_code
        hod_display = hod_profile.name or hod_key or 'UNKNOWN'
        users_under_hod = UserProfile.objects.filter(roles__name='user', hod_name__iexact=hod_key)
        total_users = users_under_hod.count()
        profile_complete = sum(1 for p in users_under_hod if p.profile_updated)
        qpr_complete = sum( 1 for p in users_under_hod if QPRRecord.objects.filter( user=p.user, quarter=current_quarter, year=current_year, is_submitted=True ).exists())
        completion_pct = int((qpr_complete / total_users) * 100) if total_users > 0 else 0
        hod_stats.append({
            'hod_name': str(hod_display).upper(),
            'total_employees': total_users,
            'profile_completed': profile_complete,
            'qpr_completed': qpr_complete,
            'completion_percentage': completion_pct,
        })
    unique_hod_names = set(UserProfile.objects.filter(roles__name='user').exclude(hod_name__isnull=True).values_list('hod_name', flat=True))
    actual_hod_names = set(UserProfile.objects.filter(roles__name='hod').values_list('hod_name', flat=True))
    uncovered = unique_hod_names - actual_hod_names
    for hod_name in sorted(uncovered):
        users_under_hod = UserProfile.objects.filter(roles__name='user', hod_name__iexact=hod_name)
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
    pending_requests = ManagerRequest.objects.filter(status='pending', hod__roles__name='user')
    context = {
        'role': 'admin',  # Explicitly set role for template to avoid showing other roles' content
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
    if not user_has_role(request.user, 'admin'): return redirect('/')
    if request.method == 'POST':
        emp_code = request.POST.get('emp_code', '').strip()
        if not emp_code:
            messages.error(request, 'Employee code is required')
        else:
            # Check if employee code exists in registered users
            try:
                profile = UserProfile.objects.get(employee_code=emp_code)
                display_name = profile.name or profile.user.get_full_name() or profile.user.username
                if profile.roles.filter(name='hod').exists():
                    messages.error(request, 'This user is already assigned a HOD role')
                else:
                    # Assign HOD role (sync to both profile and user)
                    hod_role = Role.objects.get(name='hod')
                    user_role_obj = Role.objects.get(name='user')
                    profile.roles.add(hod_role, user_role_obj)
                    profile.approval_status = 'approved'
                    # Ensure CustomUser.roles is in sync
                    try:
                        profile.user.roles.add(hod_role, user_role_obj)
                        profile.user.save()
                    except Exception:
                        pass
                    profile.hod_name = display_name
                    profile.profile_updated = True
                    profile.save()
                    messages.success(request, f'HOD {display_name} created!')
                    return redirect('qpr_admin_dashboard')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User has not registered or entered employee code is incorrect')
    return render(request, 'qpr/admin_create_hod.html')

@login_required
def admin_create_manager(request):
    if not user_has_role(request.user, 'admin'): return redirect('/')
    if request.method == 'POST':
        emp_code = request.POST.get('emp_code', '').strip()
        if not emp_code:
            messages.error(request, 'Employee code is required')
        else:
            # Check if employee code exists in registered users
            try:
                profile = UserProfile.objects.get(employee_code=emp_code)
                display_name = profile.name or profile.user.get_full_name() or profile.user.username
                if profile.roles.filter(name='manager').exists():
                    messages.error(request, 'This user is already assigned a Manager role')
                else:
                    # Assign Manager role (sync to both profile and user)
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
    return render(request, 'qpr/admin_create_manager.html')

# def api_get_employee_details(request):
#     """API endpoint to fetch employee details by employee code"""
#     emp_code = request.GET.get('emp_code', '').strip()
    
#     if not emp_code:
#         return JsonResponse({'error': 'Employee code is required'}, status=400)
    
#     try:
#         profile = UserProfile.objects.get(employee_code=emp_code)
#         # Return profile display name and existing roles so admin UI can decide actions.
#         roles = list(profile.roles.values_list('name', flat=True))
#         display_name = profile.name or profile.user.get_full_name() or profile.user.username
#         return JsonResponse({
#             'success': True,
#             'name': display_name,
#             'employee_code': profile.employee_code,
#             'roles': roles or ['user']
#         })
#     except UserProfile.DoesNotExist:
#         return JsonResponse({
#             'error': 'User has not registered or entered employee code is incorrect'
#         }, status=404)


@login_required
def api_create_office(request):
    """Admin-only endpoint to create an office (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if not user_has_role(request.user, 'admin'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    code = request.POST.get('office_code', '').strip()
    name = request.POST.get('office_name', '').strip()
    if not code or not name:
        return JsonResponse({'error': 'Office code and name are required'}, status=400)

    from .models import Office
    office, created = Office.objects.get_or_create(code=code, defaults={'name': name})
    if not created:
        return JsonResponse({'error': 'Office code already exists'}, status=400)
    return JsonResponse({'success': True, 'code': office.code, 'name': office.name})


def api_list_offices(request):
    """Return list of offices for dropdowns"""
    from .models import Office
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
    employee_code_filter = request.GET.get('employee_code', '').strip()
    name_filter = request.GET.get('name', '').strip()
    quarter_filter = request.GET.get('quarter', '').strip()
    year_filter = request.GET.get('year', '').strip()
    if not quarter_filter:
        quarter_filter = get_current_quarter()
    if not year_filter:
        year_filter = get_current_year_label()

    hods = UserProfile.objects.filter(roles__name='hod').order_by('name')
    hod_groups = []
    
    # Collect all unique quarters and years for filter dropdowns
    all_qpr_records = QPRRecord.objects.all()
    all_quarters = sorted(set(all_qpr_records.values_list('quarter', flat=True).filter(quarter__isnull=False)))
    all_years = sorted(set(all_qpr_records.values_list('year', flat=True).filter(year__isnull=False)), reverse=True)

    current_year = get_current_year_label()

    if current_year not in all_years:
        all_years.insert(0, current_year)
    
    from .models import Employee
    for hod_profile in hods:
        users_under_hod = UserProfile.objects.filter(roles__name='user', hod_name=hod_profile.hod_name).order_by('name')
        user_details = []
        for user_profile in users_under_hod:
            # employee_code may be None; normalize to empty string
            emp_code_val = (user_profile.employee_code or '').strip()
            if employee_code_filter and employee_code_filter.lower() not in emp_code_val.lower():
                continue

            user_name = (user_profile.name or user_profile.user.get_full_name() or user_profile.user.username) or ''

            # Try to fill missing name from Employee table when profile name is blank or 'None'
            emp_record = None
            if (not user_name) or user_name.strip().lower() in ['', 'none']:
                # Attempt integer conversion for codes with leading zeros (e.g., '003')
                if emp_code_val:
                    try:
                        emp_int = int(emp_code_val)
                        emp_record = Employee.objects.filter(empcode=emp_int).first()
                    except Exception:
                        emp_record = Employee.objects.filter(empcode=emp_code_val).first()
                # fallback: try to match by username
                if not emp_record:
                    emp_record = Employee.objects.filter(empcode=user_profile.user.username).first()
                if emp_record and emp_record.ename:
                    user_name = emp_record.ename

            if name_filter and name_filter.lower() not in (user_name or '').lower():
                continue

            qpr_record = QPRRecord.objects.filter( user=user_profile.user, quarter=quarter_filter, year=year_filter ).first()

            # Fill office info: prefer profile, then latest QPR, else Employee.hname
            office_name_val = user_profile.office_name or (qpr_record.officeName if qpr_record else '')
            office_code_val = user_profile.office_code or (qpr_record.officeCode if qpr_record else '')

            if (not office_name_val or office_name_val.strip() == '') and emp_record:
                office_name_val = getattr(emp_record, 'hname', '') or office_name_val

            user_details.append({
                'emp_code': user_profile.employee_code,
                'name': user_name,
                'email': user_profile.user.email,
                'office_name': office_name_val or 'Not Set',
                'office_code': office_code_val or 'Not Set',
                'quarter': quarter_filter,
                'year': year_filter,
                'qpr_status': qpr_record.status if qpr_record else 'Not Submitted',
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
    """Restored Full Action Logic: Archive, Unarchive, Unlock

    This handler accepts either a user id (for user-level actions) or a QPR id
    for the special-case action 'unlock_qpr'. We handle 'unlock_qpr' first to
    avoid attempting to resolve a CustomUser for a QPR id (which caused 404s).
    """
    # Special-case: treat provided id as QPR id when unlocking a QPR
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
    # First try treating it as user id
        target_user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
    # If not found, treat it as employee_code
        profile = get_object_or_404(UserProfile, employee_code=user_id)
        target_user = profile.user

    lang = request.session.get('lang', 'en')
    
    if action in ['archive', 'unarchive']:
        if not (user_has_role(request.user, ['admin']) or request.user.is_superuser):
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
        emp = Employee.objects.filter( empcode=int(target_user.profile.employee_code)).first()
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
    if not profile or profile.approval_status != 'approved':
        messages.error(request, "Access Denied: Your account must be approved by your HOD before you can submit a QPR.")
        return redirect('dashboard')
    
    # Auto-create current financial year if it doesn't exist
    ensure_current_financial_year()
    
    profile_office_name = profile.office_name if profile and profile.office_name else ''
    profile_office_code = profile.office_code if profile and profile.office_code else ''
    profile_phone = profile.phone if profile and profile.phone else ''
    profile_email = profile.email if profile and profile.email else (request.user.get_email() if hasattr(request.user, 'get_email') else '')

    # Build a list of already used quarters for this user (quarter, year, record_id)
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

    # Determine current quarter for preselection using server local date (respects TIME_ZONE)
    today = timezone.localdate()
    month = today.month
    
    # Quarter mapping (Indian FY Apr-Mar): Apr-Jun -> Jun 30, Jul-Sep -> Sep 30, Oct-Dec -> Dec 31, Jan-Mar -> Mar 31
    if 4 <= month <= 6:
        current_quarter = '30 जून / Jun 30'
    elif 7 <= month <= 9:
        current_quarter = '30 सितंबर / Sep 30'
    elif 10 <= month <= 12:
        current_quarter = '31 दिसंबर / Dec 31'
    else:
        current_quarter = '31 मार्च / Mar 31'

    # Compute current financial year string (e.g. "2025-2026") where fiscal year runs Apr-Mar
    fiscal_year_start = today.year - 1 if month < 4 else today.year
    current_financial_year = f"{fiscal_year_start}-{fiscal_year_start + 1}"

    # Build financial_years list from FinancialYear table's earliest recorded start
    # up to the current fiscal year. If none exist, start from current fiscal year.
    fy_qs = FinancialYear.objects.filter(is_active=True)
    min_start = fy_qs.aggregate(Min('start_year'))['start_year__min']
    if min_start is None:
        min_start = fiscal_year_start
    financial_years = []
    for s in range(min_start, fiscal_year_start + 1):
        financial_years.append({'start_year': s, 'end_year': s + 1})

    context.update({
        'current_quarter': current_quarter,
        'current_year': current_financial_year,
        'financial_years': financial_years,
        'user_role': getattr(request.user, 'role', None),
        'server_month': today.month,
        'server_year': today.year,
        'profile_language_region': profile.language_region if profile else '',
    })
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
    
    # Get section7 data (notings data) using safe attribute access
    section7 = getattr(qpr_record, 'section7', None)
    if section7:
        total_notes = getattr(section7, 'total_pages', 0) or 0
        hindi_notes = getattr(section7, 'hindi_pages', 0) or 0
    else:
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
def hod_detail_list(request):
    if not user_has_role(request.user, 'hod'): return redirect('/')
    # Determine hod_name from profile (fallback to profile.name)
    hod_profile = getattr(request.user, 'profile', None)
    hod_name = (hod_profile.hod_name or hod_profile.name) if hod_profile else None
    hod_name = hod_name.strip() if hod_name else None

    # Robustly include users who have the 'user' role on either UserProfile or CustomUser
    if hod_name:
        user_role_q = Q(roles__name='user') | Q(user__roles__name='user')
        users_under_hod = UserProfile.objects.filter(
            user_role_q & Q(hod_name__iexact=hod_name)
        ).select_related('user').distinct()
    else:
        users_under_hod = UserProfile.objects.filter(user=request.user).select_related('user')
    users_data = []
    current_quarter = get_current_quarter()
    current_year = get_current_year_label()
    for user_profile in users_under_hod:
        user = user_profile.user
        qpr_records = user.qpr_records.all()
        office_code = ''
        office_name = ''
        if qpr_records.exists():
            first_qpr = qpr_records.first()
            office_code = first_qpr.officeCode
            office_name = first_qpr.officeName

        # Normalize employee code and try to fill missing profile fields from Employee
        emp_code_val = (user_profile.employee_code or '').strip()
        emp_record = None
        if emp_code_val:
            try:
                emp_int = int(emp_code_val)
                from .models import Employee
                emp_record = Employee.objects.filter(empcode=emp_int).first()
            except Exception:
                from .models import Employee
                emp_record = Employee.objects.filter(empcode=emp_code_val).first()

        # Build display name: prefer profile.name, then full name, then Employee.ename, then username
        display_name = user_profile.name or user.get_full_name() or ''
        if not display_name or display_name.strip().lower() in ['', 'none']:
            if emp_record and emp_record.ename:
                display_name = emp_record.ename
            else:
                display_name = user.username

        # Fill office info: prefer profile, then QPR, then Employee.hname
        office_name_val = user_profile.office_name or office_name or ''
        office_code_val = user_profile.office_code or office_code or ''
        if (not office_name_val or office_name_val.strip() == '') and emp_record:
            office_name_val = getattr(emp_record, 'hname', '') or office_name_val

        has_pending = ManagerRequest.objects.filter(hod=user, request_type='qpr', status='pending').exists()
        current_qpr = qpr_records.filter( quarter=current_quarter, year=current_year ).first()
        is_quarterly_frozen = current_qpr.is_quarterly_frozen if current_qpr else False
        users_data.append({
            'profile': user_profile, 'user': user, 'employee_code': user_profile.employee_code,
            'name': display_name, 'office_code': office_code_val or 'Not Set', 'office_name': office_name_val or 'Not Set',
            'profile_complete': user_profile.profile_updated, 'qpr_complete': current_qpr.is_submitted if current_qpr else False,
            'qpr_record_id': current_qpr.id if current_qpr else None,
            'has_pending_edit_request': has_pending,
            'is_quarterly_frozen': is_quarterly_frozen
        })
    context = {'users_data': users_data, 'hod_name': hod_name, 'current_quarter': current_quarter, 'current_year': current_year}
    response = render(request, 'qpr/hod_detail_list.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
def toggle_freeze_qpr(request, qpr_record_id):
    """HOD can freeze/unfreeze quarterly QPR reports"""
    if not user_has_role(request.user, 'hod'):
        return redirect('/')
    
    if request.method != 'POST':
        return redirect('qpr_hod_detail_list')
    
    try:
        qpr_record = QPRRecord.objects.get(id=qpr_record_id, frequency='quarterly')
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Quarterly record not found'}, status=404)
    
    # Check if HOD is authorized (record belongs to user in their department)
    hod_profile = getattr(request.user, 'profile', None)
    hod_name = (hod_profile.hod_name or hod_profile.name) if hod_profile else None
    
    if hod_name:
        user_profile = getattr(qpr_record.user, 'profile', None)
        record_hod_name = (user_profile.hod_name or user_profile.name) if user_profile else None
        if record_hod_name != hod_name.strip():
            return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    # Check if we're at quarter end (can only freeze at quarter end)
    today = date.today()
    quarter_end_dates = get_quarter_end_dates()  # You'll need to create this helper
    
    is_at_quarter_end = today >= quarter_end_dates['current']
    
    # Toggle freeze (can always unfreeze, but can only freeze at quarter-end)
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
    
    # Redirect back to HOD detail list
    return redirect('qpr_hod_detail_list')

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
                        qpr_record_id=record.pk,
                        status='approved'
                    ).exists()
            d['can_edit'] = not record.is_submitted or edit_approved
            d['edit_approved'] = edit_approved
            # include cumulative aggregates (daily/weekly/monthly/quarterly) for convenience
            try:
                d['cumulative'] = compute_cumulative_for_record(record)
            except Exception:
                d['cumulative'] = {}
            data.append(d)
        return JsonResponse(data, safe=False)
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            year = data.get('year', '').strip()

            today = timezone.localdate()
            current_start = today.year if today.month >= 4 else today.year - 1

            if year:
                try:
                    selected_start = int(year.split('-')[0])
                except:
                    return JsonResponse({'error': 'Invalid year format'}, status=400)

                if selected_start > current_start:
                    return JsonResponse({'error': 'Future financial year not allowed'}, status=400)
            record_id = data.get('id')
            details = data.get('details', {})
            if record_id:
                record = QPRRecord.objects.get(pk=record_id, user=request.user)
                record.officeName = data.get('officeName', '')
                year = data.get('year', '').strip()
                quarter = data.get('quarter', '').strip()

                allowed_quarters = get_allowed_quarters(year)

                if quarter and quarter not in allowed_quarters:
                    return JsonResponse({'error': 'Invalid quarter selection'}, status=400)
                # Remove mask characters from officeCode before saving
                record.officeCode = (data.get('officeCode', '') or '').replace('*', '')
                record.region = data.get('region', '')
                record.quarter = data.get('quarter', '')
                # frequency and explicit period
                # Frequency & period are server-determined; ignore client-provided values
                record.status = data.get('status', 'Draft')
                record.phone = data.get('phone', '')
                record.email = data.get('email', '')
                record.is_submitted = (record.status == 'Submitted')

                # Determine period for this record (prefer stored period, otherwise infer from quarter/year)
                ps = getattr(record, 'period_start', None)
                pe = getattr(record, 'period_end', None)
                if not ps or not pe:
                    try:
                        ps, pe = _quarter_label_to_daterange(record.quarter, record.year or '')
                    except Exception:
                        ps, pe = (None, None)

                # Check for overlaps excluding this record itself
                if ps and pe and is_period_overlapping(request.user, ps, pe, exclude_id=record.pk):
                    return JsonResponse({'error': 'This update overlaps with an existing report.'}, status=400)

                record.period_start = ps
                record.period_end = pe

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
                        qpr_record_id=record.pk,
                        status='approved'
                    ).first()
                    if approved_edit_request:
                        approved_edit_request.status = 'used'
                        approved_edit_request.save()
                _save_section_data(record, details)
            else:
                is_submitted = (data.get('status', 'Draft') == 'Submitted')

                # Use client-provided frequency + date to compute canonical period
                frequency = (data.get('frequency') or '').strip()
                selected_date_str = (data.get('selected_date') or '').strip()

                if not frequency:
                    return JsonResponse({'error': 'Frequency is required'}, status=400)

                if frequency in ['daily', 'weekly', 'monthly'] and not selected_date_str:
                    return JsonResponse({'error': 'Date is required for the selected frequency'}, status=400)

                try:
                    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else None
                except Exception:
                    return JsonResponse({'error': 'Invalid date'}, status=400)

                # --- Validation: reject Sundays, far-future dates, and any future quarter/financial year ---
                if selected_date:
                    try:
                        today = timezone.localdate()
                        # Reject Sundays (weekday() == 6)
                        if selected_date.weekday() == 6:
                            return JsonResponse({'error': 'Selected date cannot be a Sunday'}, status=400)

                        # Reject dates more than 30 days ahead from today
                        if selected_date > (today + timedelta(days=30)):
                            return JsonResponse({'error': 'Selected date cannot be more than 30 days in the future'}, status=400)

                        # Reject dates that fall in a future quarter/financial year relative to today
                        try:
                            cur_q_start, cur_q_end = _get_quarter_range_for_date(today)
                            sel_q_start, sel_q_end = _get_quarter_range_for_date(selected_date)
                            # If selected quarter starts after current quarter start, it's a future quarter/year
                            if sel_q_start > cur_q_start:
                                return JsonResponse({'error': 'Next quarter / financial year entries not allowed'}, status=400)
                        except Exception:
                            # If quarter calculation fails, do not block on this check
                            pass
                    except Exception:
                        return JsonResponse({'error': 'Invalid date'}, status=400)

                # Validate provided frequency is allowed for this user on selected_date
                availability = _allowed_frequencies_for_date(request.user, selected_date)
                if frequency not in availability['allowed']:
                    return JsonResponse({
                        'error': f'Frequency "{frequency}" not allowed for this date. Allowed: {availability["allowed"]}',
                        'allowed_frequencies': availability['allowed'],
                        'missing_week': availability.get('missing_week', [])
                    }, status=400)

                # Compute canonical period for the supplied frequency/date/quarter/year
                ps, pe = compute_period(
                    frequency,
                    selected_date=selected_date,
                    quarter=data.get('quarter'),
                    year=data.get('year')
                )
                # duplicate-check diagnostics removed

                existing = QPRRecord.objects.filter(
                    user=request.user,
                    frequency__iexact=frequency
                )

                # existing period_start values logging removed
                # Overlap check for the computed period
                if ps and pe and is_period_overlapping(request.user, ps, pe):
                    return JsonResponse({'error': 'This period overlaps with an already submitted report.'}, status=400)

                # Ensure uniqueness for the computed period/frequency
                exists = QPRRecord.objects.filter(user=request.user, frequency__iexact=frequency, period_start=ps, is_submitted=True)

                # Defensive: if client provided quarter/year, validate and filter
                quarter = data.get('quarter', '').strip()
                year = data.get('year', '').strip() or None
                allowed_quarters = get_allowed_quarters(year)
                if quarter and quarter not in allowed_quarters:
                    return JsonResponse({'error': f'Invalid quarter. Allowed: {allowed_quarters}'}, status=400)

                if quarter:
                    exists = exists.filter(quarter=quarter)
                    if year:
                        exists = exists.filter(year=year)

                if exists.exists():
                    return JsonResponse({'error': 'A report for this period already exists.'}, status=400)

                record = QPRRecord.objects.create(
                    user=request.user, officeName=data.get('officeName', ''), officeCode=(data.get('officeCode', '') or '').replace('*',''),
                    region=data.get('region', ''), quarter=data.get('quarter', ''), year=data.get('year', ''), status=data.get('status', 'Draft'),
                    frequency=frequency,
                    period_start=ps,
                    period_end=pe,
                    phone=data.get('phone', ''), email=data.get('email', ''), is_submitted=is_submitted
                )
                _save_section_data(record, details)
            return JsonResponse({'id': record.pk, 'message': 'Saved successfully!'})
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
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return JsonResponse({'error': 'Record not found'}, status=404)

    # Determine roles
    is_owner = record.user == request.user
    is_manager = user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser
    is_hod = user_has_role(request.user, ['hod'])

    # Basic permission check
    if not (is_owner or is_manager or is_hod):
        return JsonResponse({'error': 'Access denied'}, status=403)

    # Additional HOD restriction
    if not is_manager and is_hod:
        hod_office = getattr(request.user.profile, 'office_code', None)

        hod_employees = UserProfile.objects.filter(
            office_code=hod_office,
            hod_name=request.user.username
        )

        if not hod_employees.filter(user_id=record.user_id).exists():
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    data = serialize_qpr_record(record)
    # Compute edit approval flags consistent with api_records
    edit_approved = False
    has_pending_edit_request = False
    
    if record.is_submitted:
        edit_approved = (
            ManagerRequest.objects.filter(user=record.user, request_type='qpr', status='approved').exists()
            or bool(getattr(record.user, 'is_edit_allowed', False))
        )
        if not edit_approved:
            edit_approved = EditRequest.objects.filter(
                user=record.user,
                request_type='qpr',
                qpr_record_id=record.pk,
                status='approved'
            ).exists()
        
        # Check if there's a pending edit request
        has_pending_edit_request = EditRequest.objects.filter(
            user=record.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            status='pending'
        ).exists()
    
    # User can edit if they own it and it's not submitted, or if they have edit approval
    data['can_edit'] = (record.user == request.user and not record.is_submitted) or edit_approved
    data['edit_approved'] = edit_approved
    data['has_pending_edit_request'] = has_pending_edit_request
    data['is_submitted'] = record.is_submitted
    # include cumulative aggregates for the record (used by the detail view JS)
    try:
        data['cumulative'] = compute_cumulative_for_record(record)
    except Exception:
        data['cumulative'] = {}

    return JsonResponse(data, safe=False)


@login_required
def print_qpr_report(request, record_id):
    """Render a server-side printable version of the QPR record (matches view)."""
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
    # Render server-side template with the same fields used by report_detail
    return render(request, 'qpr/print_report.html', {'r': data})


@login_required
def api_period_summary(request):
    """Return per-period aggregates (daily/weekly/monthly/quarterly) for the requested quarter/year.
    Query params: quarter (label like '31 मार्च / Mar 31') and year (label like '2025-2026').
    If not provided, uses current quarter/year.
    """
    user = request.user
    quarter = request.GET.get('quarter') or get_current_quarter()
    year = request.GET.get('year') or get_current_year_label()
    # User-selected frequency controls aggregation source. One of: daily, weekly, monthly, quarterly
    selected_frequency = (request.GET.get('frequency') or 'daily').lower()

    # Determine default region from user's profile (Language Region)
    default_region = ''
    try:
        profile = getattr(user, 'profile', None)
        if profile and getattr(profile, 'language_region', None):
            default_region = profile.language_region
    except Exception:
        default_region = ''

    # Determine quarter date range
    try:
        q_start, q_end = _quarter_label_to_daterange(quarter, year)
    except Exception:
        return JsonResponse({'error': 'Invalid quarter/year'}, status=400)

    # Build daily list for working days (Mon-Sat) within quarter
    daily = []
    cur = q_start
    while cur <= q_end:
        if cur.weekday() <= 5:  # Mon-Sat
            # Determine totals according to selected frequency policy.
            # If the user explicitly selected a higher-level frequency, use that source for aggregation;
            # otherwise use the lower-level (daily) source for daily rows.
            if selected_frequency == 'daily':
                totals = _aggregate_records_for_range(user, cur, cur, source_frequency='daily')
                # check if a daily record exists for that exact date
                rec_daily = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start=cur).first()
                exists_daily = bool(rec_daily)
                covered_by = None
                region = getattr(rec_daily, 'region', None) if rec_daily else ''
            else:
                # use the selected_frequency as the source for this date
                src = selected_frequency
                totals = _aggregate_records_for_range(user, cur, cur, source_frequency=src)
                # check if a source-frequency record covers this date
                rec_src = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact=src, period_start__lte=cur, period_end__gte=cur).first()
                exists_daily = False
                covered_by = src if rec_src else None
                region = getattr(rec_src, 'region', None) if rec_src else ''

            daily.append({
                'period_start': cur.isoformat(),
                'period_end': cur.isoformat(),
                'totals': totals,
                'has_daily': exists_daily,
                'covered_by': covered_by,
                'region': region or default_region or ''
            })
        cur = cur + timedelta(days=1)

    # Build weekly list (Mon-Sat weeks) covering quarter
    weekly = []
    # start from Monday of the week containing quarter start (may be before q_start)
    w_start = q_start - timedelta(days=q_start.weekday())
    while w_start <= q_end:
        w_end = w_start + timedelta(days=5)  # Mon -> Sat
        display_start = max(w_start, q_start)
        display_end = min(w_end, q_end) 
        # determine the actual overlap range within the quarter for counts/totals
        actual_start = display_start
        actual_end = display_end
        # Weekly totals: if the user selected weekly view use weekly records, otherwise sum daily records
        if selected_frequency == 'weekly':
            totals = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='weekly')
        else:
            totals = _aggregate_records_for_range(user, actual_start, actual_end, source_frequency='daily')
        # count daily submitted in this week's in-quarter range
        daily_count = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(actual_start, actual_end)).count()
        expected_days = 0
        for d in range((actual_end - actual_start).days + 1):
            dt = actual_start + timedelta(days=d)
            if dt.weekday() <= 5 and q_start <= dt <= q_end:
                expected_days += 1
        missing_days = max(0, expected_days - daily_count)
        weekly_submitted = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='weekly', period_start__lte=display_start, period_end__gte=display_end).exists()
        # determine region for week: prefer weekly record, else any daily within
        weekly_rec = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='weekly', period_start__lte=display_start, period_end__gte=display_end).first()
        region_week = getattr(weekly_rec, 'region', '') if weekly_rec else ''
        if not region_week:
            cand = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(actual_start, actual_end)).first()
            region_week = getattr(cand, 'region', '') if cand else ''
        
        weekly.append({
            'period_start': display_start.isoformat(),
            'period_end': display_end.isoformat(),
            'totals': totals,
            'daily_count': daily_count,
            'expected_days': expected_days,
            'missing_days': missing_days,
            'weekly_submitted': weekly_submitted,
            'region': region_week or default_region or ''
        })
        # move to next week's Monday
        w_start = w_start + timedelta(days=7)

    # Monthly list for months inside quarter
    monthly = []
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
        # Monthly totals: if the user selected monthly use monthly records, otherwise sum weekly records
        if selected_frequency == 'monthly':
            totals = _aggregate_records_for_range(user, month_start, month_end, source_frequency='monthly')
        else:
            totals = _aggregate_records_for_range(user, month_start, month_end, source_frequency='weekly')
        daily_count = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(month_start, month_end)).count()
        monthly_submitted = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='monthly', period_start__lte=month_start, period_end__gte=month_end).exists()
        monthly_rec = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='monthly', period_start__lte=month_start, period_end__gte=month_end).first()
        region_month = getattr(monthly_rec, 'region', '') if monthly_rec else ''
        if not region_month:
            cand = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='daily', period_start__range=(month_start, month_end)).first()
            region_month = getattr(cand, 'region', '') if cand else ''
        monthly.append({
            'period_start': month_start.isoformat(),
            'period_end': month_end.isoformat(),
            'totals': totals,
            'daily_count': daily_count,
            'monthly_submitted': monthly_submitted,
            'region': region_month or default_region or ''
        })
        # move to first of next month
        if m.month == 12:
            m = date(m.year + 1, 1, 1)
        else:
            m = date(m.year, m.month + 1, 1)

    # Quarterly totals
    # Quarterly totals: if the user selected quarterly use quarterly records, otherwise sum monthly records
    if selected_frequency == 'quarterly':
        quarterly_totals = _aggregate_records_for_range(user, q_start, q_end, source_frequency='quarterly')
    else:
        quarterly_totals = _aggregate_records_for_range(user, q_start, q_end, source_frequency='monthly')
    quarterly_submitted = QPRRecord.objects.filter(user=user, is_submitted=True, frequency__iexact='quarterly', period_start=q_start, period_end=q_end).exists()

    return JsonResponse({
        'quarter_label': quarter,
        'year_label': year,
        'quarter_start': q_start.isoformat(),
        'quarter_end': q_end.isoformat(),
        'daily': daily,
        'weekly': weekly,
        'monthly': monthly,
        'quarterly': {'period_start': q_start.isoformat(), 'period_end': q_end.isoformat(), 'totals': quarterly_totals, 'submitted': quarterly_submitted}
    }, safe=False)

@login_required
@csrf_exempt
def request_edit_api(request):
    """API endpoint for requesting QPR edits"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request_type = data.get('request_type')
            record_id = data.get('record_id')
            reason = data.get('reason', '')
            
            if not request_type or not record_id:
                return JsonResponse({'error': 'Missing required fields'}, status=400)
            
            # For QPR requests, create an EditRequest
            if request_type == 'qpr':
                try:
                    record = QPRRecord.objects.get(pk=record_id, user=request.user)
                except QPRRecord.DoesNotExist:
                    return JsonResponse({'error': 'Record not found'}, status=404)
                
                # Check if there's already a pending request
                existing = EditRequest.objects.filter(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    status__in=['pending', 'approved']
                ).first()
                
                if existing:
                    return JsonResponse({'error': 'Request already exists with status: ' + existing.status}, status=400)
                
                # Create the EditRequest
                edit_req = EditRequest.objects.create(
                    user=request.user,
                    request_type='qpr',
                    qpr_record_id=record_id,
                    reason=reason,
                    status='pending'
                )
                
                # Send notification to manager(s)
                from .utils import send_system_email
                manager_office = record.officeCode
                managers = UserProfile.objects.filter(
                    office_code=manager_office,
                    roles__name='manager'
                ).select_related('user')
                
                for profile in managers:
                    try:
                        msg = f"Employee {request.user.get_full_name() or request.user.username} has requested permission to edit their QPR submission.\n\nReason: {reason}"
                        send_system_email(
                            profile.user,
                            request,
                            'manager_alert',
                            extra_context={'body_text': msg, 'subject': 'QPR Edit Request'}
                        )
                    except Exception:
                        # on email failure, continue without raising
                        pass
                
                return JsonResponse({'success': True, 'message': 'Edit request submitted to manager'})
            
            # For profile requests, create the old way with ManagerRequest
            admin_users = User.objects.filter(profile__roles__name='admin')
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

        # Use profile.employee_code when available (some users have non-numeric username)
        user_empcode = None
        try:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.employee_code:
                user_empcode = int(profile.employee_code)
            else:
                user_empcode = int(request.user.username)
        except Exception:
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

        # Resolve the numeric employee code from the user's profile when possible
        try:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.employee_code:
                user_empcode = int(profile.employee_code)
            else:
                user_empcode = int(request.user.username)
        except Exception:
            return Response({"detail": "Username must be numeric."}, status=400)

        # Check if a record already exists
        existing_emp = Employee.objects.filter(empcode=user_empcode).first()
        if existing_emp:
            # Return the existing record so user can edit it
            serializer = EmployeeSerializer(existing_emp)
            return Response(
                {
                    "id": existing_emp.id,
                    "message": "A record already exists for you. Edit your saved draft instead of creating a new record.",
                    "data": serializer.data
                },
                status=200
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

        # Get user's employee code from profile or username
        try:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.employee_code:
                user_empcode = int(profile.employee_code)
            else:
                user_empcode = int(request.user.username)
        except (ValueError, TypeError):
            return Response({"error": "Invalid employee code"}, status=400)
        
        # USER can only edit their own records, admins/managers can edit others
        if user_role(request.user) == 'user' and int(getattr(emp, 'empcode', 0)) != user_empcode:
            return Response({"error": "Unauthorized"}, status=403)

        serializer = EmployeeSerializer(emp, data=request.data)

        if serializer.is_valid():
            serializer.save(lastupdate=timezone.now())
            return Response(serializer.data)

        return Response(serializer.errors, status=400)
    def delete(self, request, pk):
        emp = self.get_object(pk)
        if not emp:
            return Response({"error": "Not found"}, status=404)

        # Get user's employee code from profile or username
        try:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.employee_code:
                user_empcode = int(profile.employee_code)
            else:
                user_empcode = int(request.user.username)
        except (ValueError, TypeError):
            return Response({"error": "Invalid employee code"}, status=400)
        
        # USER can only delete their own records, admins/managers can delete others
        if user_role(request.user) == 'user' and int(getattr(emp, 'empcode', 0)) != user_empcode:
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
    profile = getattr(request.user, 'profile', None)
    from .models import Employee

    # If an Employee record already exists for this user's empcode, let them edit it.
    emp_record = None
    if profile and profile.employee_code:
        emp_record = Employee.objects.filter(empcode=profile.employee_code).first()

    if request.method == 'POST':
        if emp_record:
            form = EmployeeForm(request.POST, instance=emp_record)
        else:
            form = EmployeeForm(request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            # Ensure empcode is set from user's profile and do not auto-submit; user saves manually
            if profile and profile.employee_code:
                obj.empcode = profile.employee_code
            obj.lastupdate = timezone.now()
            obj.save()
            messages.success(request, 'Employee record saved successfully.')
            return redirect('dashboard')
    else:
        if emp_record:
            form = EmployeeForm(instance=emp_record)
        else:
            initial = {}
            if profile and profile.employee_code:
                initial['empcode'] = profile.employee_code
            initial['ename'] = request.user.first_name or request.user.username
            form = EmployeeForm(initial=initial)

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
            
            # Send notification to admins
            admins = CustomUser.objects.filter(roles__name='admin', is_active=True)
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
    
    # Check if quarterly is frozen
    if qpr_record.frequency == 'quarterly' and qpr_record.is_quarterly_frozen:
        messages.error(request, translate_text("This quarterly report is frozen and cannot be edited.", lang))
        return redirect('qpr_report_detail', record_id=record_id)
    
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
                admins = CustomUser.objects.filter(roles__name='admin', is_active=True)
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
    if not user_has_role(request.user, ['admin']):
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
    if not user_has_role(request.user, ['manager', 'admin']):
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
            if user_role(request.user) == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
        except Exception as e:
            messages.error(request, translate_text(f"Error approving request: {str(e)}", lang))
            if user_role(request.user) == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
    
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/approve_edit_request.html', context)


@login_required
def reject_edit_request(request, request_id):
    """Manager/Admin rejects an edit request"""
    if not user_has_role(request.user, ['manager', 'admin']):
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
            if user_role(request.user) == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
        except Exception as e:
            messages.error(request, translate_text(f"Error rejecting request: {str(e)}", lang))
            if user_role(request.user) == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('qpr_admin_dashboard')
    
    context = {'edit_request': edit_request, 'current_lang': lang}
    return render(request, 'qpr/reject_edit_request.html', context)


def typing_data_report(request):
    lang = request.session.get('lang', 'en')
    typing_reports = TypingUsageReport.objects.select_related(
        'qpr_record__user__profile',
        'qpr_record__section7'
    ).all()
    data = []
    for report in typing_reports:
        qpr_record = report.qpr_record
        user_profile = qpr_record.user.profile if qpr_record.user else None
        employee_name = (user_profile.name if user_profile else None) or (qpr_record.user.username if qpr_record.user else 'Unknown')
        designation = 'N/A'
        office_code = (user_profile.office_code if user_profile else None) or 'N/A'

        try:
            if user_profile and user_profile.employee_code:
                employee = Employee.objects.get(empcode=user_profile.employee_code)
                designation = employee.designation or 'N/A'
                office_code = (user_profile.office_code if user_profile else None) or 'N/A'
        except Employee.DoesNotExist:
            pass
        
        # Get section7 data using safe attribute access
        section7 = getattr(qpr_record, 'section7', None)
        if section7:
            total_notes = getattr(section7, 'total_pages', 0) or 0
            hindi_notes = getattr(section7, 'hindi_pages', 0) or 0
        else:
            total_notes = 0
            hindi_notes = 0
        
        notes_hindi_percentage = (hindi_notes / total_notes * 100) if total_notes > 0 else 0
        words_hindi_percentage = ((report.hindi_words or 0) / (report.total_words or 1) * 100) if (report.total_words and report.total_words > 0) else 0
        
        data.append({
            'serial_no': len(data) + 1,
            'employee_name': employee_name,
            'designation': designation,
            'office_code': office_code,
            'total_notes': total_notes,
            'hindi_notes': hindi_notes,
            'notes_hindi_percentage': round(notes_hindi_percentage, 2),
            'total_words': report.total_words or 0,
            'hindi_words': report.hindi_words or 0,
            'words_hindi_percentage': round(words_hindi_percentage, 2),
            'year': qpr_record.year,
            'quarter': qpr_record.quarter,
        })
    
    context = {
        'typing_data': data,
        'years': sorted(set(r['year'] for r in data if r['year']), reverse=True),
        'quarters': sorted(set(r['quarter'] for r in data if r['quarter'])),
        'current_lang': lang,
    }
    return render(request, 'qpr/typing_data_report.html', context)


# ==================== USER HOD SELECTION ====================

@login_required
def api_user_change_hod(request):
    """API endpoint for users to change their assigned HOD"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        new_hod_name = data.get('hod_name', '').strip()
        
        if not new_hod_name:
            return JsonResponse({'success': False, 'error': 'HOD name is required'}, status=400)
        
        # Check if user is HOD or Manager - they shouldn't be able to change HOD
        if user_has_role(request.user, ['hod', 'manager', 'admin']):
            return JsonResponse({'success': False, 'error': 'Only users can change their HOD'}, status=403)
        
        # Get user's profile
        try:
            profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User profile not found'}, status=404)
        
        # Verify the selected HOD exists (check both profile.roles and the user's roles)
        hod_exists = UserProfile.objects.filter(
            Q(roles__name='hod') | Q(user__roles__name='hod'),
            hod_name__iexact=new_hod_name
        ).exists()
        if not hod_exists:
            return JsonResponse({'success': False, 'error': 'Selected HOD does not exist'}, status=400)
        
        # Update the HOD
        old_hod = profile.hod_name
        profile.hod_name = new_hod_name
        profile.save()
        
        return JsonResponse({
            'success': True, 
            'message': f'HOD changed successfully from {old_hod or "None"} to {new_hod_name}',
            'new_hod': new_hod_name
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== HOD MANAGEMENT (ADMIN ONLY) ====================

@csrf_exempt
@login_required
def api_update_hod(request):
    """API endpoint to update HOD name and employee code (Admin only)"""
    if not user_has_role(request.user, ['admin']):
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
                hod_profile = UserProfile.objects.get(employee_code=old_employee_code, roles__name='hod')
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
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=400)
def send_reminder_email(request, user_id):
    user_profile = getattr(request.user, 'profile', None)
    if not user_profile or not user_profile.roles.filter(name='hod').exists(): 
        return redirect('/')
        
    if request.method == 'POST':
        target_user = get_object_or_404(CustomUser, id=user_id)
        lang = request.session.get('lang', 'en')
        target_profile = getattr(target_user, 'profile', None)
        if target_profile and target_profile.hod_name == user_profile.hod_name:
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
    return FileResponse(buffer, as_attachment=True, filename='employee_records.pdf')


@login_required
def manager_report(request):
    """Manager Report - Display status of last 4 quarterly progress reports"""
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
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
        # expected users list (use user_id to avoid mismatches)
        # Include users who have the 'user' role on either UserProfile or CustomUser
        # Use distinct() to avoid duplicate user_ids from join duplication
        expected_user_ids = list(UserProfile.objects.filter(office_code=manager_office).filter(
            Q(roles__name='user') | Q(user__roles__name='user')
        ).values_list('user_id', flat=True).distinct())
        # Ensure we only consider non-null user ids
        expected_user_ids = [u for u in expected_user_ids if u is not None]
        users_count = len(expected_user_ids)
    logger.debug('manager_report: manager=%s office=%s users_count=%s', request.user.username, manager_office, users_count)

    # Find quarter-year groups for which number of distinct submitted user records == users_count
    report_data = []
    if manager_office and users_count > 0:
        q_groups = QPRRecord.objects.filter(officeCode=manager_office, is_submitted=True) \
            .values('year', 'quarter') \
            .annotate(submitted_users=Count('user', distinct=True)) \
            .order_by('-year', '-quarter')

        for g in q_groups:
            # get distinct user ids who submitted for this quarter
            submitted_user_ids = list(QPRRecord.objects.filter(officeCode=manager_office, year=g['year'], quarter=g['quarter'], is_submitted=True).values_list('user', flat=True).distinct())
            # require that all expected users have submitted (subset test)
            if set(expected_user_ids).issubset(set([u for u in submitted_user_ids if u is not None])):
                rep = QPRRecord.objects.filter(officeCode=manager_office, year=g['year'], quarter=g['quarter'], is_submitted=True).order_by('-updated_at').first()
                status_date = rep.updated_at.strftime('%b %d, %Y – %I:%M %p') if rep and rep.updated_at else ''
                report_data.append({
                    'year': g['year'] or '2025–2026',
                    'quarter': g['quarter'] or 'Q1',
                    'office_name': rep.officeName if rep else manager_office,
                    'status_title': 'Received by Official Language Department',
                    'status_date': status_date,
                    'id': rep.pk if rep else None,
                    'edit_count': EditRequest.objects.filter(qpr_record_id=rep.pk, status__in=['approved','used']).count() if rep else 0,
                    'submitted_users': len([u for u in submitted_user_ids if u is not None]),
                    'expected_users': users_count,
                })

    context = {
        'office_code': manager_office or '',
        'qpr_reports': report_data,
    }
    
    return render(request, 'qpr/manager_report.html', context)


@login_required
def manager_report_detail(request, year, quarter):
    """Show list of users who submitted for given quarter and year, grouped by HOD."""
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

    # Normalize year: if year contains '2025' treat as empty string (DB stores year='')
    normalized_year = year

    # Find submitted QPRs matching the office, normalized year, and quarter
    submitted = QPRRecord.objects.filter(officeCode=manager_office, year=normalized_year, quarter=quarter, is_submitted=True)
    submitted_users_count = submitted.values('user').distinct().count()
    total_users = users_qs.count()

    # Flag indicating whether all users have submitted (used to control view behavior)
    all_submitted = submitted_users_count >= total_users

    # Build grouping by HOD and include every employee; mark submitted status
    grouped = {}

    # Map submitted records by user id
    submitted_map = {r.user.id: r for r in submitted if r.user is not None}

    for up in users_qs:
        user = up.user
        rec = submitted_map.get(getattr(user, 'id', None))
        hod = up.hod_name or 'Unassigned'
        if hod not in grouped:
            grouped[hod] = []
        grouped[hod].append({
            'name': up.name or user.username,
            'empcode': up.employee_code,
            'email': up.email or '',
            'submitted': bool(rec),
            'submitted_at': rec.updated_at if rec else None,
            'qpr_record_id': rec.id if rec else None,
        })

    context = {
        'year': year if year else '2025-2026', # <--- Add the fallback here too!
        'quarter': quarter,
        'office_code': manager_office,
        'grouped': grouped,
        'all_submitted': all_submitted,
        'submitted_users_count': submitted_users_count,
        'total_users': total_users,
    }
    
    return render(request, 'qpr/manager_report_detail.html', context)


@login_required
def qpr_certificate(request, record_id):
    """Render a printable certificate for a QPR record (open in new tab and print)."""
    try:
        rec = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    # Permission: only manager/admin or same office manager can view
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    # If user is manager, ensure office matches their profile where possible
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
    # Delegate to manager_report_detail using the record's year and quarter
    return manager_report_detail(request, rec.year, rec.quarter)


@login_required
def certificate_form_view(request, record_id):
    """Auto-populate certificate data and redirect to display"""
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    # Only manager/admin can view certificate for submitted records
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    # Get or create certificate data with auto-populated values from record
    cert_data, created = CertificateData.objects.get_or_create(
        qpr_record=record,
        defaults={
            'financial_year': record.year if record.year else '2025-2026',
            'quarter_ending': record.quarter if record.quarter else '',
        }
    )
    
    # Redirect to Part II form view (manager fills Part II here)
    return redirect('certificate_part2', record_id=record.id)





@login_required
def certificate_display_view(request, record_id):
    """Display the certificate in Enclosure format"""
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    # Only manager/admin can view certificate
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    # Get certificate data
    cert_data = CertificateData.objects.filter(qpr_record=record).first()
    if not cert_data:
        # Redirect to form if certificate data doesn't exist
        return redirect('certificate_form', record_id=record.id)

    context = {
        'record': record,
        'cert_data': cert_data,
    }
    return render(request, 'qpr/certificate_display.html', context)


@login_required
def certificate_part2_view(request, record_id):
    """Render and save Part II of QPR (manager-facing form).
    GET: render the `certificate_part2.html` form pre-filled when data exists.
    POST: accept JSON payload and create/update QPRPartTwo + related rows.
    Enforce at most 2 manager edits for existing records (uses QPRRecord.cert_edit_count).
    """
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        return redirect('manager_report')

    # Permission: only manager/admin
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    if request.method == 'GET':
        part2 = getattr(record, 'part2', None)

        # Prepare JSON payload for client-side prefill, include all scalar fields
        part2_data = {}
        if part2:
            part2_data = {
                'financial_year': part2.financial_year,
                'is_notified_rule_10_4': bool(part2.is_notified_rule_10_4),
                'total_sub_offices': part2.total_sub_offices,
                'notified_sub_offices': part2.notified_sub_offices,
                'computer_training_total_staff': part2.computer_training_total_staff,
                'computer_training_trained': part2.computer_training_trained,
                'computer_training_working': part2.computer_training_working,
                'total_computers': part2.total_computers,
                'hindi_enabled_computers': part2.hindi_enabled_computers,
                'officials_issued_rule_8_4_orders': part2.officials_issued_rule_8_4_orders,
                'training_total_duration_hours': part2.training_total_duration_hours,
                'training_imparted_hindi': part2.training_imparted_hindi,
                'training_imparted_english': part2.training_imparted_english,
                'training_imparted_mixed': part2.training_imparted_mixed,
                'sec8_total_sections': part2.sec8_total_sections,
                'sec8_inspected_sections': part2.sec8_inspected_sections,
                'sec8_total_sub_offices': part2.sec8_total_sub_offices,
                'sec8_inspected_sub_offices': part2.sec8_inspected_sub_offices,
                'magazines_total': part2.magazines_total,
                'magazines_hindi': part2.magazines_hindi,
                'magazines_english': part2.magazines_english,
                'expenditure_total_books': str(part2.expenditure_total_books),
                'expenditure_hindi_books': str(part2.expenditure_hindi_books),
                'hindi_event_start_date': part2.hindi_event_start_date.isoformat() if part2.hindi_event_start_date else '',
                'hindi_event_end_date': part2.hindi_event_end_date.isoformat() if part2.hindi_event_end_date else '',
                'seminar_date': part2.seminar_date.isoformat() if part2.seminar_date else '',
                'seminar_subject': part2.seminar_subject,
                'other_activities_date': part2.other_activities_date.isoformat() if part2.other_activities_date else '',
                'other_activities_subject': part2.other_activities_subject,
                'staff_knowledge': list(part2.staff_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
                'hindi_posts': list(part2.hindi_posts.values('designation', 'sanctioned', 'vacant')),
                'typing_knowledge': list(part2.typing_knowledge.values('category', 'total_no', 'trained_in_hindi', 'work_in_hindi', 'yet_to_be_trained')),
                'translation_knowledge': list(part2.translation_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
                'code_manuals': list(part2.codes_manuals.values('category', 'total_no', 'bilingual_no')),
                'officers_work': list(part2.officers_work.values('level', 'total_officers', 'knowledge_of_hindi', 'not_doing', 'doing_upto_25', 'doing_26_to_50', 'doing_51_to_75', 'doing_more_76', 'doing_cent_percent')),
                'websites': list(part2.websites.values('url', 'status')),
                'chairperson': {
                    'name': part2.chairperson_name or '',
                    'designation': part2.chairperson_designation or '',
                    'phone': part2.chairperson_phone or '',
                    'fax': part2.chairperson_fax or '',
                    'email': part2.chairperson_email or ''
                }
            }

        context = {
            'record': record,
            'part2': part2,
            'part2_json': json.dumps(part2_data)
        }
        return render(request, 'qpr/certificate_part2.html', context)

    # POST - save JSON payload
    try:
        payload = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)
    # Determine action: 'save' or 'submit'
    action = payload.get('action', 'save')

    existing = getattr(record, 'part2', None)
    if existing:
        part2 = existing
        # If already submitted and not unlocked for editing, block edits (except admins)
        if part2.is_submitted and not record.is_editing_allowed and not (user_has_role(request.user, ['admin']) or request.user.is_superuser):
            return JsonResponse({'success': False, 'error': 'This Part II has been submitted and is locked for editing.'}, status=403)
    else:
        from decimal import Decimal
        part2 = QPRPartTwo.objects.create(qpr_record=record, financial_year=payload.get('financial_year', record.year or ''))

    # Update scalar fields on part2
    # Map known scalar fields if present
    if 'financial_year' in payload:
        part2.financial_year = payload.get('financial_year')
    if 'is_notified_rule_10_4' in payload:
        part2.is_notified_rule_10_4 = bool(payload.get('is_notified_rule_10_4'))
    if 'total_sub_offices' in payload:
        part2.total_sub_offices = int(payload.get('total_sub_offices') or 0)
    if 'notified_sub_offices' in payload:
        part2.notified_sub_offices = int(payload.get('notified_sub_offices') or 0)
    # Additional scalar fields
    if 'computer_training_total_staff' in payload:
        part2.computer_training_total_staff = int(payload.get('computer_training_total_staff') or 0)
    if 'computer_training_trained' in payload:
        part2.computer_training_trained = int(payload.get('computer_training_trained') or 0)
    if 'computer_training_working' in payload:
        part2.computer_training_working = int(payload.get('computer_training_working') or 0)
    if 'total_computers' in payload:
        part2.total_computers = int(payload.get('total_computers') or 0)
    if 'hindi_enabled_computers' in payload:
        part2.hindi_enabled_computers = int(payload.get('hindi_enabled_computers') or 0)
    if 'officials_issued_rule_8_4_orders' in payload:
        part2.officials_issued_rule_8_4_orders = int(payload.get('officials_issued_rule_8_4_orders') or 0)
    if 'training_total_duration_hours' in payload:
        part2.training_total_duration_hours = int(payload.get('training_total_duration_hours') or 0)
    if 'training_imparted_hindi' in payload:
        part2.training_imparted_hindi = int(payload.get('training_imparted_hindi') or 0)
    if 'training_imparted_english' in payload:
        part2.training_imparted_english = int(payload.get('training_imparted_english') or 0)
    if 'training_imparted_mixed' in payload:
        part2.training_imparted_mixed = int(payload.get('training_imparted_mixed') or 0)
    if 'sec8_total_sections' in payload:
        part2.sec8_total_sections = int(payload.get('sec8_total_sections') or 0)
    if 'sec8_inspected_sections' in payload:
        part2.sec8_inspected_sections = int(payload.get('sec8_inspected_sections') or 0)
    if 'sec8_total_sub_offices' in payload:
        part2.sec8_total_sub_offices = int(payload.get('sec8_total_sub_offices') or 0)
    if 'sec8_inspected_sub_offices' in payload:
        part2.sec8_inspected_sub_offices = int(payload.get('sec8_inspected_sub_offices') or 0)
    if 'magazines_total' in payload:
        part2.magazines_total = int(payload.get('magazines_total') or 0)
    if 'magazines_hindi' in payload:
        part2.magazines_hindi = int(payload.get('magazines_hindi') or 0)
    if 'magazines_english' in payload:
        part2.magazines_english = int(payload.get('magazines_english') or 0)
    if 'expenditure_total_books' in payload:
        try:
            part2.expenditure_total_books = Decimal(str(payload.get('expenditure_total_books') or 0))
        except Exception:
            part2.expenditure_total_books = Decimal('0.00')
    if 'expenditure_hindi_books' in payload:
        try:
            part2.expenditure_hindi_books = Decimal(str(payload.get('expenditure_hindi_books') or 0))
        except Exception:
            part2.expenditure_hindi_books = Decimal('0.00')
    # Dates and text
    if 'hindi_event_start_date' in payload:
        part2.hindi_event_start_date = payload.get('hindi_event_start_date') or None
    if 'hindi_event_end_date' in payload:
        part2.hindi_event_end_date = payload.get('hindi_event_end_date') or None
    if 'seminar_date' in payload:
        part2.seminar_date = payload.get('seminar_date') or None
    if 'seminar_subject' in payload:
        part2.seminar_subject = payload.get('seminar_subject') or ''
    if 'other_activities_date' in payload:
        part2.other_activities_date = payload.get('other_activities_date') or None
    if 'other_activities_subject' in payload:
        part2.other_activities_subject = payload.get('other_activities_subject') or ''

    # Other scalar fields can be mapped similarly if included in payload
    part2.save()

    # If action is 'submit' mark submitted and lock editing
    if action == 'submit':
        from django.utils import timezone
        part2.is_submitted = True
        part2.submitted_at = timezone.now()
        part2.submitted_by = request.user
        part2.save()
        # Lock editing until manager unlocks via manager table
        record.is_editing_allowed = False
        record.save(update_fields=['is_editing_allowed'])

    # Replace staff_knowledge rows
    if 'staff_knowledge' in payload:
        part2.staff_knowledge.all().delete()
        for item in payload.get('staff_knowledge', []):
            StaffHindiKnowledge.objects.create(
                report=part2,
                category=item.get('category', ''),
                officers_count=int(item.get('officers_count') or 0),
                employees_count=int(item.get('employees_count') or 0),
                total_count=int(item.get('total_count') or 0)
            )

    # Typing/Stenography rows
    if 'typing_knowledge' in payload:
        part2.typing_knowledge.all().delete()
        for item in payload.get('typing_knowledge', []):
            from website.models import TypingStenographyKnowledge
            TypingStenographyKnowledge.objects.create(
                report=part2,
                category=item.get('category', ''),
                total_no=int(item.get('total_no') or 0),
                trained_in_hindi=int(item.get('trained_in_hindi') or 0),
                work_in_hindi=int(item.get('work_in_hindi') or 0),
                yet_to_be_trained=int(item.get('yet_to_be_trained') or 0)
            )

    # Translation knowledge
    if 'translation_knowledge' in payload:
        part2.translation_knowledge.all().delete()
        for item in payload.get('translation_knowledge', []):
            from website.models import TranslationKnowledge
            TranslationKnowledge.objects.create(
                report=part2,
                category=item.get('category', ''),
                officers_count=int(item.get('officers_count') or 0),
                employees_count=int(item.get('employees_count') or 0),
                total_count=int(item.get('total_count') or 0)
            )

    # Code/manuals
    if 'code_manuals' in payload:
        part2.codes_manuals.all().delete()
        for item in payload.get('code_manuals', []):
            from website.models import CodeManualStandardForms
            CodeManualStandardForms.objects.create(
                report=part2,
                category=item.get('category', ''),
                total_no=int(item.get('total_no') or 0),
                bilingual_no=int(item.get('bilingual_no') or 0)
            )

    # Officers work (sections 11 & 12)
    if 'officers_work' in payload:
        part2.officers_work.all().delete()
        for item in payload.get('officers_work', []):
            from website.models import OfficersWorkInHindi
            OfficersWorkInHindi.objects.create(
                report=part2,
                level=item.get('level', ''),
                total_officers=int(item.get('total_officers') or 0),
                knowledge_of_hindi=int(item.get('knowledge_of_hindi') or 0),
                not_doing=int(item.get('not_doing') or 0),
                doing_upto_25=int(item.get('doing_upto_25') or 0),
                doing_26_to_50=int(item.get('doing_26_to_50') or 0),
                doing_51_to_75=int(item.get('doing_51_to_75') or 0),
                doing_more_76=int(item.get('doing_more_76') or 0),
                doing_cent_percent=int(item.get('doing_cent_percent') or 0)
            )

    # Websites
    if 'websites' in payload:
        part2.websites.all().delete()
        for w in payload.get('websites', []):
            from website.models import WebsiteDetail
            if not w.get('url'): continue
            WebsiteDetail.objects.create(
                report=part2,
                url=w.get('url'),
                status=w.get('status') or ''
            )

    # Chairperson / contact
    if 'chairperson' in payload:
        ch = payload.get('chairperson') or {}
        part2.chairperson_name = ch.get('name') or ''
        part2.chairperson_designation = ch.get('designation') or ''
        part2.chairperson_phone = ch.get('phone') or ''
        part2.chairperson_fax = ch.get('fax') or ''
        part2.chairperson_email = ch.get('email') or ''
        part2.save()

    # Replace hindi_posts rows
    if 'hindi_posts' in payload:
        part2.hindi_posts.all().delete()
        for p in payload.get('hindi_posts', []):
            if not p.get('designation'):
                continue
            HindiPost.objects.create(
                report=part2,
                designation=p.get('designation'),
                sanctioned=int(p.get('sanctioned') or 0),
                vacant=int(p.get('vacant') or 0)
            )

    return JsonResponse({'success': True, 'message': 'Part II saved', 'edit_count': record.cert_edit_count})


@login_required
def certificate_part2_print_view(request, record_id):
    try:
        record = QPRRecord.objects.get(pk=record_id)
    except QPRRecord.DoesNotExist:
        raise Http404()

    # Permission: manager/admin or read-only for others who can view
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser or request.user == record.user):
        raise PermissionDenied()

    part2 = getattr(record, 'part2', None)
    part2_data = {}
    if part2:
        part2_data = {
            'financial_year': part2.financial_year,
            'is_notified_rule_10_4': bool(part2.is_notified_rule_10_4),
            'total_sub_offices': part2.total_sub_offices,
            'notified_sub_offices': part2.notified_sub_offices,
            'staff_knowledge': list(part2.staff_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
            'hindi_posts': list(part2.hindi_posts.values('designation', 'sanctioned', 'vacant')),
            'typing_knowledge': list(part2.typing_knowledge.values('category', 'total_no', 'trained_in_hindi', 'work_in_hindi', 'yet_to_be_trained')),
            'translation_knowledge': list(part2.translation_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
            'code_manuals': list(part2.codes_manuals.values('category', 'total_no', 'bilingual_no')),
            'officers_work': list(part2.officers_work.values('level', 'total_officers', 'knowledge_of_hindi', 'not_doing', 'doing_upto_25', 'doing_26_to_50', 'doing_51_to_75', 'doing_more_76', 'doing_cent_percent')),
            'websites': list(part2.websites.values('url', 'status')),
            'chairperson': {
                'name': part2.chairperson_name or '',
                'designation': part2.chairperson_designation or '',
                'phone': part2.chairperson_phone or '',
                'fax': part2.chairperson_fax or '',
                'email': part2.chairperson_email or ''
            }
        }

    context = {'record': record, 'part2': part2, 'part2_data': part2_data}
    return render(request, 'qpr/certificate_part2_print.html', context)


@login_required
def manager_report_edit_view(request, record_id):
    """Unlock ONLY certificate Part-II for editing (max 2 times)"""

    try:

        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

        if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        try:
            record = QPRRecord.objects.get(pk=record_id)
        except QPRRecord.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Record not found'}, status=404)

        # Verify manager office
        mgr_office = getattr(request.user.profile, 'office_code', None)
        if mgr_office != record.officeCode:
            return JsonResponse({'success': False, 'error': 'Unauthorized office'}, status=403)

        # LIMIT EDITS
        if record.cert_edit_count >= 2:
            return JsonResponse({
                'success': False,
                'error': 'Maximum edit attempts (2) reached'
            })

        # increase edit count
        record.cert_edit_count += 1
        record.is_editing_allowed = True
        record.save(update_fields=['cert_edit_count', 'is_editing_allowed'])

        # unlock ONLY the certificate
        part2 = getattr(record, 'part2', None)

        if part2:
            part2.is_submitted = False
            part2.save(update_fields=['is_submitted'])

        return JsonResponse({
            'success': True,
            'message': f'Certificate unlocked. Edit attempt {record.cert_edit_count}/2',
            'edit_count': record.cert_edit_count
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        
from gtts import gTTS
import os
from django.conf import settings

def generate_captcha_audio(text):
    # This creates the audio from the captcha text
    tts = gTTS(text=text, lang='en')
    filename = os.path.join(settings.MEDIA_ROOT, 'captcha_audio.mp3')
    tts.save(filename)
    return filename

@login_required
def print_all_qpr_reports(request, year, quarter):
    """Aggregates Part 1, Certificate, and Part 2 for all submitted employees for printing."""
    if not (user_has_role(request.user, ['manager', 'admin']) or request.user.is_superuser):
        return redirect('/')

    # Determine manager's office
    manager_office = getattr(request.user.profile, 'office_code', None)
    if not manager_office:
        first = QPRRecord.objects.filter(user=request.user).first()
        manager_office = first.officeCode if first else None

    if not manager_office:
        return redirect('manager_report')

    normalized_year = year
    
    # Fetch all submitted QPRs for this office, year, and quarter
    submitted_qprs = QPRRecord.objects.filter(
        officeCode=manager_office, 
        year=normalized_year, 
        quarter=quarter, 
        is_submitted=True
    ).select_related('user', 'part2', 'certificate_data').order_by('user__username')

    # Submitted QPRs count: suppressed debug output

    all_reports_data = []
    
    for record in submitted_qprs:
        # 1. Part 1 Data
        part1_data = serialize_qpr_record(record)
        
        # 2. Certificate Data
        cert_data = getattr(record, 'certificate_data', None)
        
        # 3. Part 2 Data
        part2 = getattr(record, 'part2', None)
        part2_data = {}
        if part2:
            part2_data = {
                'financial_year': part2.financial_year,
                'is_notified_rule_10_4': bool(part2.is_notified_rule_10_4),
                'total_sub_offices': part2.total_sub_offices,
                'notified_sub_offices': part2.notified_sub_offices,
                'staff_knowledge': list(part2.staff_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
                'hindi_posts': list(part2.hindi_posts.values('designation', 'sanctioned', 'vacant')),
                'typing_knowledge': list(part2.typing_knowledge.values('category', 'total_no', 'trained_in_hindi', 'work_in_hindi', 'yet_to_be_trained')),
                'translation_knowledge': list(part2.translation_knowledge.values('category', 'officers_count', 'employees_count', 'total_count')),
                'code_manuals': list(part2.codes_manuals.values('category', 'total_no', 'bilingual_no')),
                'officers_work': list(part2.officers_work.values('level', 'total_officers', 'knowledge_of_hindi', 'not_doing', 'doing_upto_25', 'doing_26_to_50', 'doing_51_to_75', 'doing_more_76', 'doing_cent_percent')),
                'websites': list(part2.websites.values('url', 'status')),
                'chairperson': {
                    'name': part2.chairperson_name or '',
                    'designation': part2.chairperson_designation or '',
                    'phone': part2.chairperson_phone or '',
                    'fax': part2.chairperson_fax or '',
                    'email': part2.chairperson_email or ''
                }
            }

        all_reports_data.append({
            'record': record,
            'part1': part1_data,
            'cert': cert_data,
            'part2': part2,
            'part2_data': part2_data,
            'employee_name': record.user.get_full_name() or record.user.username,
            'emp_code': getattr(record.user.profile, 'employee_code', 'N/A') if hasattr(record.user, 'profile') else 'N/A'
        })

    context = {
        'year': year,
        'quarter': quarter,
        'reports': all_reports_data,
        'office_code': manager_office
    }
    writer = PdfWriter()
    temp_files = []

    # ---------- PART 1 : All Employee QPR Reports ----------
    for item in all_reports_data:

        html_string = render_to_string(
            "qpr/print_report.html",
            {"r": item['part1'], "record": item['record'], "current_lang": request.session.get("lang", "en")}
        )

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        HTML( string=html_string, base_url=request.build_absolute_uri("/")).write_pdf(tmp.name)
        reader = PdfReader(tmp.name)
        for page in reader.pages:
            writer.add_page(page)
        temp_files.append(tmp.name)


    # ---------- PART 2 : Manager Form ----------
    manager_item = all_reports_data[0] if all_reports_data else None

    if manager_item and manager_item['part2']:

        html_string = render_to_string(
            "qpr/print_certificate_part2.html",
            {
                "record": manager_item['record'],
                "part2": manager_item['part2'],
                "part2_data": manager_item['part2_data'],
                "current_lang": request.session.get("lang", "en")
            }
        )


        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        HTML( string=html_string, base_url=request.build_absolute_uri("/")).write_pdf(tmp.name)
        reader = PdfReader(tmp.name)
        for page in reader.pages:
            writer.add_page(page)
        temp_files.append(tmp.name)


    # ---------- PART 3 : Final Certificate ----------
    if manager_item and manager_item['cert']:

        html_string = render_to_string(
            "qpr/certificate.html",
            {
                "record": manager_item['record'],
                "cert_data": manager_item['cert'],
                "current_lang": request.session.get("lang", "en")
            }
        )

 
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        HTML( string=html_string, base_url=request.build_absolute_uri("/")).write_pdf(tmp.name)
        reader = PdfReader(tmp.name)
        for page in reader.pages:
            writer.add_page(page)
        temp_files.append(tmp.name)


    # ---------- FINAL MERGED PDF ----------
    # ---------- FINAL PDF ----------
    output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")

    with open(output.name, "wb") as f:
        writer.write(f)

    pdf_file = open(output.name, "rb")

    response = FileResponse(
        pdf_file,
        content_type="application/pdf"
    )

    response["Content-Disposition"] = f'inline; filename="QPR_{quarter}_{year}.pdf"'

    return response

# Debug helper: returns current user/session info (useful to verify AJAX session & roles)
def debug_whoami(request):
    try:
        user = request.user
        data = {
            'is_authenticated': user.is_authenticated,
            'username': user.username if user and user.is_authenticated else None,
            'roles': user_get_all_roles(user) if user and user.is_authenticated else [],
            'profile_office_code': getattr(getattr(user, 'profile', None), 'office_code', None),
            'session_key': request.session.session_key,
            'method': request.method,
        }
        return JsonResponse({'success': True, 'whoami': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@login_required
def process_user_approval(request, profile_id, action):
    if not user_has_role(request.user, ['hod', 'admin']):
        messages.error(request, "Unauthorized action.")
        return redirect('dashboard')

    target_profile = get_object_or_404(UserProfile, id=profile_id)
    
    if action == 'approve':
        target_profile.approval_status = 'approved'
        target_profile.save()
        # Send Email: "Approved! Verify login & go to QPR Form"
        send_system_email(target_profile.user, request, 'accepted_alert') 
        messages.success(request, f"User {target_profile.employee_code} approved.")
        
    elif action == 'reject':
        target_profile.approval_status = 'rejected'
        target_profile.save()
        # Send Email: "Rejected. Please update details or register again."
        send_system_email(target_profile.user, request, 'rejected_alert') # You'll need to add this template to utils.py
        messages.warning(request, f"User {target_profile.employee_code} rejected.")

    return redirect('qpr_hod_dashboard')