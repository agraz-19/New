from django.urls import path
from . import views
from .views import (
    SubmitDraftAPI,
    home,
    employee_form,
    EmployeeListCreateAPI,
    EmployeeDetailAPI
)

urlpatterns = [
    # Frontend
    path('', home, name='home'),
    path('employee-form/', employee_form, name='employee_form'),

    # API
    path('api/employees/', EmployeeListCreateAPI.as_view(), name='employee_list_create'),
    path('api/employees/<int:pk>/', EmployeeDetailAPI.as_view(), name='employee_detail'),
    path("api/employees/submit/", SubmitDraftAPI.as_view()),
    path('translate/', views.translation_form, name='translation_form'),  # Translation form page
    path('translate_text/', views.translate_text, name='translate_text'), 
]
