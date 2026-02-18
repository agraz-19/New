from django.urls import path, include
from website import views
from website.views import (
    CustomLoginView, signup, ForgotPasswordView, VerifyOTPView, ResetPasswordView,
    EmployeeListCreateAPI, EmployeeDetailAPI, SubmitDraftAPI, custom_logout
)

urlpatterns = [
    path('captcha/', include('captcha.urls')),
    
    # Core & Auth
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'), # Central Router
    
    path('login/', CustomLoginView.as_view(), name='login'),
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
    path('qpr/hod/dashboard/', views.qpr_hod_dashboard, name='qpr_hod_dashboard'),
    path('qpr/user/dashboard/', views.user_dashboard, name='qpr_user_dashboard'),

    # --- USER QPR WORKFLOW ---
    path('qpr/profile/update/', views.user_profile, name='qpr_user_profile'),
    path('qpr/office/', views.user_office_form, name='qpr_user_office'),
    path('qpr/form/', views.qpr_form, name='qpr_form'),
    path('qpr/reports/', views.report_list, name='qpr_report_list'),
    path('qpr/reports/<int:record_id>/', views.report_detail, name='qpr_report_detail'),

    # --- HOD WORKFLOW ---
    path('qpr/hod/details/', views.hod_detail_list, name='qpr_hod_detail_list'),
    path('qpr/hod/requests/', views.hod_manager_requests, name='qpr_hod_requests'),

    path('qpr/admin/employees/', views.admin_employee_list, name='qpr_admin_employee_list'),
    path('qpr/admin/create-hod/', views.admin_create_hod, name='qpr_admin_create_hod'),
    path('qpr/admin/approve/<int:request_id>/', views.admin_approve_request, name='qpr_admin_approve'),
    path('update-designation/<int:user_id>/', views.update_designation, name='update_designation'),
    path('action/<int:user_id>/<str:action>/', views.manage_user_action, name='manage_user_action'),

    path('qpr/api/records/', views.api_records, name='qpr_api_records'), 
    path('qpr/api/records/<int:record_id>/', views.api_record_detail, name='api_record_detail'),
    path('qpr/api/request-edit/', views.request_edit_api, name='request_edit_api'),

    path('employee-form/', views.employee_form, name='employee_form'),
    path('api/employees/', EmployeeListCreateAPI.as_view(), name='employee_list_create_api'),
    path('api/employees/<int:pk>/', EmployeeDetailAPI.as_view(), name='employee_detail_api'),
    path('api/employees/submit/', SubmitDraftAPI.as_view(), name='submit_draft_api'),

    path('download-backup/', views.download_db_backup, name='download_db_backup'),
    path('perform/archive/<int:user_id>/', views.archive_user, name='archive_user'),
    path('perform/unarchive/<int:archive_id>/', views.unarchive_user, name='unarchive_user'),
]