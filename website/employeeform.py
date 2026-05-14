from django import forms
from .models import Employee


class EmployeeForm(forms.ModelForm):

    super_annuation_date = forms.DateField(
        label="Superannuation Date",
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date"
            }
        )
    )

    class Meta:
        model = Employee

        fields = [
            "empcode",
            "ename",
            "hname",
            "designation",
            "typing",
            "hindiproficiency",
            "gazet",
            "stenographer",
            "highest_exam",
            "olic_affiliate",
        ]

        labels = {
            "empcode": "Empcode",
            "ename": "Name in English",
            "hname": "Name in Hindi",
            "designation": "Designation",
            "typing": "Typing",
            "hindiproficiency": "Hindi Proficiency",
            "gazet": "Gazet",
            "stenographer": "Stenographer",
            "highest_exam": "Highest Hindi Exam Passed",
            "olic_affiliate": "OLIC Affiliate",
        }

        widgets = {

            "empcode": forms.TextInput(
                attrs={"class": "form-control"}
            ),

            "ename": forms.TextInput(
                attrs={"class": "form-control"}
            ),

            "hname": forms.TextInput(
                attrs={"class": "form-control"}
            ),

            # Dropdowns (choices come automatically from model)
            "designation": forms.Select(
                attrs={"class": "form-select"}
            ),

            "typing": forms.Select(
                attrs={"class": "form-select"}
            ),

            "hindiproficiency": forms.Select(
                attrs={"class": "form-select"}
            ),

            "gazet": forms.Select(
                attrs={"class": "form-select"}
            ),

            "stenographer": forms.Select(
                attrs={"class": "form-select"}
            ),

            "highest_exam": forms.Select(
                attrs={"class": "form-select"}
            ),

            "olic_affiliate": forms.Select(
                attrs={"class": "form-select"}
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # decrypt superannuation date
        if self.instance and self.instance.pk:

            decrypted_date = self.instance.get_super_annuation_date()

            if decrypted_date:
                self.fields["super_annuation_date"].initial = decrypted_date
