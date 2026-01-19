from django import forms
from .models import Employee

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        # Exclude the 'lastupdate' field since it's non-editable
        fields = ['empcode', 'ename', 'hname', 'desig', 'gazet', 'prabodh', 'praveen', 'pragya', 'parangat', 'typing', 'hindiproficiency', 'superannuationDate']
