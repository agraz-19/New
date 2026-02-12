from django import forms
from .models import Employee
PROFICIENCY_CHOICES = [
        ('', '---------'), 
        ('Passed', 'Passed'),
        ('Did not Appear', 'Did not Appear'),
    ]


class EmployeeForm(forms.ModelForm):
    # EXPLICITLY declare this field so the form knows how to handle it
    # independently of the encrypted model field.
    super_annuation_date = forms.DateField(
        label="Superannuation Date",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )

    class Meta:
        model = Employee
        # Exclude the internal encrypted field so it doesn't show up
        exclude = ["status", "encrypted_super_annuation_date"]

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
            # Widget is now handled in the field definition above
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing an existing record, we need to manually decrypt and set the initial value
        if self.instance and self.instance.pk:
            decrypted_date = self.instance.get_super_annuation_date()
            if decrypted_date:
                self.fields['super_annuation_date'].initial = decrypted_date