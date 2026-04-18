from django import urls
from django.urls import path, include
from captcha import views as captcha_views
from website import views
from website.views import (
    CustomLoginView, LoginOTPView, signup, ForgotPasswordView, VerifyOTPView, ResetPasswordView,
    custom_logout
)

urlpatterns = [
    path('captcha/', include('captcha.urls')),
    path('captcha/refresh/', captcha_views.captcha_refresh, name='captcha-refresh'),    
    # Core & Auth
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'), # Central Router
    
    path('login/', CustomLoginView.as_view(), name='login'),
    path('login/verify-otp/', LoginOTPView.as_view(), name='login_otp_step'),
    path('signup/', signup, name='signup'),
    path('logout/', custom_logout, name='logout'),

    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('resend-otp/', views.ResendOTPView.as_view(), name='resend_otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('change-password/', views.change_password, name='change_password'),

    # User Profile & Privacy
    path('profile/', views.profile_view, name='profile'),
    path('toggle-language/', views.toggle_language, name='toggle_language'),
    path('export-data/', views.export_user_data, name='export_data'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('privacy-audit/', views.privacy_audit_report, name='privacy_audit'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('privacy-audit/download/', views.download_privacy_audit, name='download_audit_pdf'),
    path('profile/freeze/', views.freeze_profile, name='freeze_profile'),
    path('profile/request-edit/', views.request_edit, name='request_edit'),

    # --- UNIFIED DASHBOARDS ---
    path('qpr/admin/dashboard/', views.admin_dashboard, name='qpr_admin_dashboard'),
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/report/', views.manager_report, name='manager_report'),
    path('manager/report/edit/<int:record_id>/', views.manager_report_edit_view, name='manager_report_edit'),
    path('manager/report/record/<int:record_id>/', views.manager_report_detail_by_record, name='manager_report_detail_by_record'),
    path('qpr/certificate/<int:record_id>/', views.qpr_certificate, name='qpr_certificate'),
    path('qpr/certificate/<int:record_id>/form/', views.certificate_form_view, name='certificate_form'),
    path('qpr/certificate/<int:record_id>/display/', views.certificate_display_view, name='certificate_display'),
    path('certificate-part2/', views.certificate_part2_view, name='certificate_part2'),
    path('qpr/certificate/<int:record_id>/part2/print/', views.certificate_part2_print_view, name='certificate_part2_print'),
    
    # Debug
    path('debug/whoami/', views.debug_whoami, name='debug_whoami'),
    path('qpr/hod/dashboard/', views.qpr_hod_dashboard, name='qpr_hod_dashboard'),
    path('qpr/user/dashboard/', views.user_dashboard, name='qpr_user_dashboard'),

    # --- USER QPR WORKFLOW ---
    path('qpr/profile/update/', views.profile_view, name='qpr_user_profile'),
    path('qpr/profile/request-edit/', views.request_profile_edit, name='request_profile_edit'),
    path('qpr/office/', views.user_office_form, name='qpr_user_office'),
    path('qpr/form/', views.qpr_form, name='qpr_form'),
    path('qpr/reports/', views.report_list, name='qpr_report_list'),
    path('qpr/reports/<int:record_id>/', views.report_detail, name='qpr_report_detail'),
    path('qpr/reports/<int:record_id>/print/', views.print_qpr_report, name='qpr_report_print'),
    path('qpr/reports/<int:record_id>/typing-usage-report/', views.typing_usage_report_form, name='typing_usage_report_form'),
    path('qpr/reports/<int:record_id>/typing-usage-report/view/', views.typing_usage_report_view, name='typing_usage_report_view'),
    path('qpr/reports/<int:record_id>/request-edit/', views.request_qpr_edit, name='request_qpr_edit'),

    # --- HOD WORKFLOW ---
    path('qpr/hod/details/', views.hod_detail_list, name='qpr_hod_detail_list'),
    path('qpr/hod/freeze/<int:qpr_record_id>/', views.toggle_freeze_qpr, name='toggle_freeze_qpr'),
    path('qpr/hod/freeze_division/', views.freeze_division_snapshot, name='freeze_division_snapshot'),
    path('qpr/hod/send-reminder/<int:user_id>/', views.send_reminder_email, name='send_reminder_email'),
    path('qpr/admin/employees/', views.admin_employee_list, name='qpr_admin_employee_list'),
    path('qpr/admin/create-hod/', views.admin_create_hod, name='qpr_admin_create_hod'),
    path('qpr/admin/create-manager/', views.admin_create_manager, name='qpr_admin_create_manager'),
    path('get-employee-form/', views.get_employee_details_form, name='get_employee_details_form'),

    path('qpr/admin/api/office-create/', views.api_create_office, name='api_create_office'),
    path('qpr/api/offices/', views.api_list_offices, name='api_list_offices'),
    path('qpr/admin/approve/<int:request_id>/', views.admin_approve_request, name='qpr_admin_approve'),
    path('qpr/admin/edit-requests/', views.admin_edit_requests, name='admin_edit_requests'),
    path('qpr/admin/approve-edit/<int:request_id>/', views.approve_edit_request, name='approve_edit_request'),
    path('qpr/admin/reject-edit/<int:request_id>/', views.reject_edit_request, name='reject_edit_request'),
    path('qpr/admin/typing-data-report/', views.typing_data_report, name='typing_data_report'),
    path('update-designation/<int:user_id>/', views.update_designation, name='update_designation'),
    path('action/<int:user_id>/<str:action>/', views.manage_user_action, name='manage_user_action'),


    path('qpr/records/', views.qpr_records_view, name='qpr_records'),
    path('qpr/records/save/', views.qpr_save_record, name='qpr_save_record'),
    path('qpr/records/delete/<int:id>/', views.qpr_delete_record, name='qpr_delete_record'),
    path('qpr/api/request-edit/', views.request_edit_api, name='request_edit_api'),


    path('download-backup/', views.download_db_backup, name='download_db_backup'),
    path('perform/archive/<int:user_id>/', views.archive_user, name='archive_user'),
    path('perform/unarchive/<int:archive_id>/', views.unarchive_user, name='unarchive_user'),

    path('manager/report/<str:year>/<path:quarter>/print-all/', views.print_all_qpr_reports, name='print_all_qpr_reports'),
    path('manager/report/<str:year>/<path:quarter>/', views.manager_report_detail, name='manager_report_detail'),
    path('manager/state-qpr/', views.manager_state_qpr, name='manager_state_qpr'),
    path("event/<str:folder>/", views.event_detail, name="event_detail"),
    path("events-admin/", views.admin_events_dashboard, name="admin_events_dashboard"),
    path("events-admin/upload/", views.admin_upload_event, name="admin_upload_event"),
    path("events-admin/delete/<str:folder>/", views.admin_delete_event, name="admin_delete_event"),
    path('events-admin/get-images/<str:folder>/', views.get_event_images, name='get_event_images'),
    path('events-admin/update-titles/', views.update_event_titles, name='update_event_titles'),
    path('get-employee-form/', views.get_employee_details_form, name='get_employee_details_form'),
    path('qpr/hod/approval/<int:profile_id>/<str:action>/', views.process_user_approval, name='process_user_approval'),
    path("events-admin/edit-titles/", views.admin_edit_event_titles, name="admin_edit_event_titles"),
    path('events-admin/<str:folder>/set-thumbnail/', views.set_thumbnail, name='set_thumbnail'),
    # Profile Change Request Workflow
    path('profile/change-request/reject/<int:request_id>/', views.reject_profile_change_hod, name='reject_profile_change'),
    path('profile/submit-change/', views.submit_profile_change_request, name='submit_profile_change_request'),
    path('profile/approve-change/<int:request_id>/', views.approve_profile_change_hod, name='approve_profile_change'),
]