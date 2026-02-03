from django import forms
from .models import Employee
PROFICIENCY_CHOICES = [
        ('', '---------'),
        ('Passed', 'Passed'),
        ('Did not Appear', 'Did not Appear'),
    ]

class EmployeeForm(forms.ModelForm):
    
    class Meta:
        model = Employee
        exclude = ["status"]

        labels = {
            "empcode": "Empcode",
            "ename": "Name in English",
            "hname": "Name in Hindi",
            "designation": "Designation",
            "gazet": "Gazet",
            "prabodh": "Prabodh",
            "praveen": "Praveen",
            "pragya": "Pragya",
            "parangat": "Parangat",
            "typing": "Typing",
            "hindiproficiency": "Hindi Proficiency",  
            "super_annuation_date":"Super Annunciation Date"
        }

        widgets = {
            "empcode": forms.TextInput(attrs={"class": "form-control"}),
            "ename": forms.TextInput(attrs={"class": "form-control"}),
            "hname": forms.TextInput(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control"}),
            "gazet": forms.Select(attrs={"class": "form-select"}),

            "prabodh": forms.Select(attrs={"class": "form-select"}, choices=PROFICIENCY_CHOICES),
            "praveen": forms.Select(attrs={"class": "form-select"}, choices=PROFICIENCY_CHOICES),
            "pragya": forms.Select(attrs={"class": "form-select"}, choices=PROFICIENCY_CHOICES),
            "parangat": forms.Select(attrs={"class": "form-select"}, choices=PROFICIENCY_CHOICES),
            "typing": forms.TextInput(attrs={"class": "form-control"}),
            "hindiproficiency": forms.TextInput(attrs={"class": "form-control"}),
            "super_annuation_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
           
        }
