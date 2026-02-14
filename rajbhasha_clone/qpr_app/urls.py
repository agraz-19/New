from django.urls import path
from . import views

urlpatterns = [

    # Dashboards
    path('dashboard/', views.user_dashboard, name='qpr_user_dashboard'),
    path('hod/dashboard/', views.hod_dashboard, name='qpr_hod_dashboard'),
    path('admin/dashboard/', views.admin_dashboard, name='qpr_admin_dashboard'),

    # User profile & office
    path('profile/', views.user_profile, name='qpr_user_profile'),
    path('office/', views.user_office_form, name='qpr_user_office'),

    # Admin
    path('admin/employees/', views.admin_employee_list, name='qpr_admin_employee_list'),
    path('admin/create-hod/', views.admin_create_hod, name='qpr_admin_create_hod'),
    path('admin/approve/<int:request_id>/', views.admin_approve_request, name='qpr_admin_approve'),

    # HOD
    path('hod/details/', views.hod_detail_list, name='qpr_hod_detail_list'),
    path('hod/requests/', views.hod_manager_requests, name='qpr_hod_requests'),

    # Reports UI
    path('', views.user_dashboard, name='qpr_form'),
    path('reports/', views.report_list, name='qpr_report_list'),
    path('reports/<int:record_id>/', views.report_detail, name='qpr_report_detail'),

    # APIs
    path('api/records/', views.api_records, name='qpr_api_records'),
    path('api/records/<int:record_id>/', views.api_record_detail, name='qpr_api_record_detail'),
    path('api/request-edit/', views.request_edit_api, name='qpr_request_edit'),
]
