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

@login_required
def user_profile(request):
    """Display and update user profile with approval workflow"""
    profile = request.user.profile
    
    # Check if profile has been submitted and needs approval for edit
    profile_submitted = profile.profile_updated
    
    # Check if user has an approved edit request for their profile
    profile_edit_approved = False
    profile_edit_pending = False
    
    if profile_submitted:
        # Look for approved profile edit requests for this user
        approved_request = ManagerRequest.objects.filter(
            hod=request.user,
            request_type='profile',
            status='approved'
        ).first()
        
        profile_edit_approved = approved_request is not None
        
        # Check for pending requests
        pending_request = ManagerRequest.objects.filter(
            hod=request.user,
            request_type='profile',
            status='pending'
        ).first()
        
        profile_edit_pending = pending_request is not None
    
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        hod_name = request.POST.get('hod_name')
        
        if not name or not email:
            messages.error(request, 'Name and email are required')
        elif not hod_name:
            messages.error(request, 'HOD name is required')
        # Check if profile is submitted and edit is not approved
        elif profile_submitted and not profile_edit_approved:
            messages.error(request, 'You cannot edit a submitted profile. Please request approval from Admin first.')
        else:
            profile.name = name
            profile.email = email
            profile.hod_name = hod_name
            profile.profile_updated = True
            profile.save()
            
            request.user.email = email
            request.user.save()
            
            # If user was editing with approval, delete the approved request
            if profile_edit_approved:
                ManagerRequest.objects.filter(
                    hod=request.user,
                    request_type='profile',
                    status='approved'
                ).delete()
                messages.success(request, 'Profile updated successfully! Please request approval if you need to make further changes.')
            else:
                messages.success(request, 'Profile updated successfully!')
            
            return redirect('user_dashboard')
    
    context = {
        'profile': profile,
        'profile_updated': profile.profile_updated,
        'profile_edit_approved': profile_edit_approved,
        'profile_edit_pending': profile_edit_pending,
        'can_edit': not profile_submitted or profile_edit_approved,
        'active_hods': get_active_hods()  # Pass dynamic HOD list
    }
    return render(request, 'user_profile.html', context)


@login_required
def user_dashboard(request):
    """User dashboard with QPR and profile status"""
    profile = request.user.profile
    
    # If profile is not updated, redirect to profile update page
    if not profile.profile_updated:
        messages.warning(request, 'Please complete your profile first!')
        return redirect('user_profile')
    
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
    return render(request, 'hod_detail_list.html', context)


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
    return render(request, 'hod_manager_requests.html', context)


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
        return redirect('admin_dashboard')# New view functions to add to views.py

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
    return render(request, 'admin_employee_list.html', context)


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
            return redirect('user_dashboard')
    
    context = {
        'profile': profile
    }
    return render(request, 'user_office_form.html', context)


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
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error creating HOD: {str(e)}')
    
    return render(request, 'admin_create_hod.html')


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
            return redirect('user_dashboard' if request.user.profile.role == 'user' else 
                          'hod_dashboard' if request.user.profile.role == 'hod' else 
                          'admin_dashboard')
    
    return render(request, 'change_password.html')


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


