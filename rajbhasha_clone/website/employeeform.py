from django import forms
from .models import Employee

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        exclude = ["status"]

        labels = {
            "empcode": "Empcode",
            "ename": "Ename",
            "hname": "Hname",
            "designation": "Designation",
            "gazet": "Gazet",
            "prabodh": "Prabodh",
            "praveen": "Praveen",
            "pragya": "Pragya",
            "parangat": "Parangat",
            "typing": "Typing",
            "hindiproficiency": "Hindi Proficiency",  # ✅ FIX
        }

        widgets = {
            "empcode": forms.TextInput(attrs={"class": "form-control"}),
            "ename": forms.TextInput(attrs={"class": "form-control"}),
            "hname": forms.TextInput(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control"}),
            "gazet": forms.Select(attrs={"class": "form-select"}),

            "prabodh": forms.TextInput(attrs={"class": "form-control"}),
            "praveen": forms.TextInput(attrs={"class": "form-control"}),
            "pragya": forms.TextInput(attrs={"class": "form-control"}),
            "parangat": forms.TextInput(attrs={"class": "form-control"}),
            "typing": forms.TextInput(attrs={"class": "form-control"}),
            "hindiproficiency": forms.TextInput(attrs={"class": "form-control"}),
        }
