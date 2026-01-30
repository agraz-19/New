from django.urls import path
from . import views
from .views import (
    SubmitDraftAPI,
    home,
    employee_form,
    EmployeeListCreateAPI,
    EmployeeDetailAPI,
    translate_api  # ✅ This is the correct automated view
)

urlpatterns = [
    # Frontend
    path('', home, name='home'),
    path('employee-form/', employee_form, name='employee_form'),

    # API Routes
    # ✅ This replaces the old 'translate/' and 'translate_text/' paths
    path('api/translate/', translate_api, name='translate_api'), 
    
    path('api/employees/', EmployeeListCreateAPI.as_view(), name='employee_list_create'),
    path('api/employees/<int:pk>/', EmployeeDetailAPI.as_view(), name='employee_detail'),
    path("api/employees/submit/", SubmitDraftAPI.as_view()),
]