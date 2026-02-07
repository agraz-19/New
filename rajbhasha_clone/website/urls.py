from django.urls import path
from .views import (
    home,
    employee_form,
    qpr_form_view,
    translate_api,
    EmployeeListCreateAPI,
    EmployeeDetailAPI,
    SubmitDraftAPI,
)

urlpatterns = [
    # Frontend
    path("", home, name="home"),
    path("employee-form/", employee_form, name="employee_form"),
    path("qpr-form/", qpr_form_view, name="qpr_form"),

    # APIs
    path("api/translate/", translate_api, name="translate_api"),

    path("api/employees/", EmployeeListCreateAPI.as_view(), name="employee_list_create"),
    path("api/employees/<int:pk>/", EmployeeDetailAPI.as_view(), name="employee_detail"),

    # ✅ SINGLE submit endpoint
    path("api/employees/submit/", SubmitDraftAPI.as_view(), name="submit_drafts"),
]
