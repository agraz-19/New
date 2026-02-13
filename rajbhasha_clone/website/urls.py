from django.urls import path, include
from website import views
from website.views import (
    CustomLoginView, signup, ForgotPasswordView, VerifyOTPView, ResetPasswordView,
    EmployeeListCreateAPI, EmployeeDetailAPI, SubmitDraftAPI, custom_logout
)

urlpatterns = [
    # Core
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'), 

    # Authentication
    path('login/', CustomLoginView.as_view(), name='login'),
    path('signup/', signup, name='signup'),
    path('logout/', custom_logout, name='logout'),

    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('resend-otp/', views.ResendOTPView.as_view(), name='resend_otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),

    # User Profile & Privacy
    path('profile/', views.profile_view, name='profile'),
    path('toggle-language/', views.toggle_language, name='toggle_language'),
    path('export-data/', views.export_user_data, name='export_data'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('privacy-audit/', views.privacy_audit_report, name='privacy_audit'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('privacy-audit/download/', views.download_privacy_audit, name='download_audit_pdf'),
    path('freeze-profile/', views.freeze_profile, name='freeze_profile'),
    path('request-edit/', views.request_edit, name='request_edit'),

    # Manager Actions
    path('manager-dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('action/<int:user_id>/<str:action>/', views.manage_user_action, name='manage_user_action'),
    path('update-designation/<int:user_id>/', views.update_designation, name='update_designation'),
    path('download-backup/', views.download_db_backup, name='download_db_backup'),

    # Employee Form (Frontend)
    path("employee-form/", views.employee_form, name="employee_form"),

    # REST APIs (Backend logic for form)
    path("api/employees/", EmployeeListCreateAPI.as_view(), name="employee_list_create"),
    path("api/employees/<int:pk>/", EmployeeDetailAPI.as_view(), name="employee_detail"),
    path("api/employees/submit/", SubmitDraftAPI.as_view(), name="submit_drafts"),

    # Captcha
    path('captcha/audio/<key>.wav', views.custom_captcha_audio, name='captcha-audio'),
    path('captcha/', include('captcha.urls')),
]

# =========================================
# CUSTOM ERROR HANDLERS
# =========================================
handler400 = 'website.views.error_400'
handler403 = 'website.views.error_403'
handler404 = 'website.views.error_404'
handler500 = 'website.views.error_500'