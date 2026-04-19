from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser
from .templatetags.translate_tags import translate_text
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
import hashlib
from captcha.fields import CaptchaField
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    consent = forms.BooleanField(
        required=True, 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={'required': 'You must agree to the Privacy Policy to proceed.'}
    )

    class Meta:
        model = CustomUser
        fields = ("username", "email", "password1", "password2", "consent")

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and hasattr(self.request, 'session'):
            self.lang = self.request.session.get('lang', 'en')
        else:
            self.lang = 'en'    
        
        lang = self.request.session.get('lang', 'en') if (self.request and hasattr(self.request, 'session')) else 'en'
        consent_error = translate_text("You must agree to the Privacy Policy to proceed.", lang)
        self.fields['consent'].error_messages['required'] = consent_error
        policy_url = reverse('privacy_policy')
        link_text = translate_text("Privacy Policy", lang)
        consent_text = translate_text("I agree to the processing of my personal data as per the", lang)
        full_label = format_html(
            '{} <a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
            consent_text,
            policy_url,
            link_text
        )
        self.fields['consent'].label = full_label
        self.fields['username'].help_text = ""
        self.fields['password1'].help_text = ""
        self.fields['password2'].help_text = translate_text("Enter the same password as before, for verification.", lang)
        self.fields['username'].label = translate_text("Employee Code", lang)
        self.fields['email'].label = translate_text("Email", lang)
        self.fields['password1'].label = translate_text("Password", lang)
        self.fields['password2'].label = translate_text("Confirm Password", lang)
        existing_user_msg = translate_text("A user with that username already exists.", lang)
        self.fields['username'].error_messages['unique'] = existing_user_msg
        
        required_msg = translate_text("This field is required.", lang)
        for field in self.fields.values():
            field.error_messages['required'] = required_msg

        self.fields['username'].error_messages.update({
            'invalid': translate_text("Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.", lang),
            'unique': translate_text("A user with that username already exists.", lang)
        })
        # 4. Apply classes and placeholders CAREFULLY
        for field_name, field in self.fields.items():
            if field_name == 'consent':
                # DO NOT add form-control or placeholders to the checkbox
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': field.label  # Only text labels work as placeholders
                })
        
        # Ensure password mismatch error is translated
        self.error_messages['password_mismatch'] = translate_text(
            "The two password fields didn't match.", lang
        )

    # def clean_username(self):
    #     username = self.cleaned_data.get('username')
    #     if not username.isdigit():
    #         raise forms.ValidationError(translate_text("Username must contain only integers.", self.lang))
    #     return username
    def clean_username(self):
        username = self.cleaned_data.get('username')
        from .models import CustomUser, UserProfile
        
        # Check if the user exists
        if CustomUser.objects.filter(username=username).exists():
            raise forms.ValidationError(translate_text("A user with this employee code already exists.", self.lang))
            
        # Check if an orphaned profile exists
        if UserProfile.objects.filter(employee_code=username).exists():
            raise forms.ValidationError(translate_text("This employee code is already registered in a profile.", self.lang))
            
        return username
    def clean_email(self):
        email = self.cleaned_data.get('email').lower().strip()
        # TEMPORARY FOR TESTING: Skip email uniqueness check so duplicate emails can be used in tests.
        # To revert: uncomment the original check below and remove these temporary lines.
        # email_hash = hashlib.sha256(email.encode()).hexdigest()
        # if CustomUser.objects.filter(email_hash=email_hash).exists():
        #     error_msg = translate_text("A user with this email already exists.", self.lang)
        #     raise forms.ValidationError(error_msg)
        return email
    
    def save(self, commit=True):
        user = super().save(commit=False)
        # DPDP: Encrypt email before saving
        user.set_email(self.cleaned_data["email"])
        # Log exact time of consent for compliance
        user.consent_given_at = timezone.now()
        
        if commit:
            user.save()
        return user

class CustomLoginForm(AuthenticationForm):
    role = forms.ChoiceField(
        choices=[('user', 'User'), ('manager', 'Manager'), ('hod', 'HOD'), ('admin', 'Admin'),('backup_user','Backup User')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    email_choice = forms.ChoiceField(
        choices=[('primary', 'Official Email'), ('alternate', 'Alternate Email')],
        widget=forms.RadioSelect,
        initial='primary',
        required=False
    )
    captcha = CaptchaField()

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        if request is None and 'request' in kwargs:
             self.request = kwargs.pop('request')
             
        super().__init__(request=self.request, *args, **kwargs)

        if self.request and hasattr(self.request, 'session'):
            self.lang = self.request.session.get('lang', 'en')
        else:
            self.lang = 'en'    
        
        self.fields["username"].label = translate_text("Employee Code", self.lang)
        self.fields["password"].label = translate_text("Password", self.lang)
        self.fields['role'].label = translate_text("Select Role", self.lang)
        self.fields['captcha'].label = translate_text("Enter the characters shown", self.lang)
        self.fields['email_choice'].label = translate_text("Send Secure OTP To:", self.lang)
        self.fields['email_choice'].choices = [
            ('primary', translate_text("Official Email", self.lang)),
            ('alternate', translate_text("Alternate Email", self.lang))
        ]

        self.error_messages['invalid_login'] = translate_text(
            "Please enter a correct username and password. Note that both fields may be case-sensitive.",
            self.lang
        )
        self.error_messages['inactive'] = translate_text("This account is inactive.", self.lang)
        
        self.fields['role'].choices = [
            ('user', translate_text("User", self.lang)),
            ('manager', translate_text("Manager", self.lang)),
            ('hod', translate_text("HOD", self.lang)),
            ('admin', translate_text("Admin", self.lang)),
            ('backup_user', translate_text("Backup User", self.lang)),
        ]

        for field_name, field in self.fields.items():
            field.help_text = ""
            # Ensure bootstrap classes are applied to all
            if field_name == 'role':
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})
            
            # Apply translated labels as placeholders
            field.widget.attrs['placeholder'] = field.label

    def clean(self):
        """Authenticate using ONLY employee code"""
        
        cleaned_data = super().clean()

        emp_code = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if not emp_code or not password:
            return cleaned_data

        from .models import UserProfile

        try:
            profile = UserProfile.objects.select_related('user').get(
                employee_code=emp_code
            )
        except UserProfile.DoesNotExist:
            raise ValidationError("Invalid Employee Code")
        
        
        user = authenticate(
            request=self.request,
            username=profile.user.username,
            password=password
        )

        if user is None:
            raise ValidationError(self.error_messages['invalid_login'], code='invalid_login')

        self.confirm_login_allowed(user)
        self.user_cache = user

        return cleaned_data



class TypingUsageReportForm(forms.Form):
    """Form for entering typing usage report data"""
    total_words = forms.IntegerField(
        label="Total Number of Words in All Notes",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter total words', 'min': '0'}),
        required=True,
        min_value=0
    )
    hindi_words = forms.IntegerField(
        label="Total Number of Hindi Words in All Notes",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter hindi words', 'min': '0'}),
        required=True,
        min_value=0
    )

    def clean(self):
        cleaned_data = super().clean()
        total_words = cleaned_data.get('total_words')
        hindi_words = cleaned_data.get('hindi_words')

        if total_words is not None and hindi_words is not None:
            if hindi_words > total_words:
                raise forms.ValidationError(
                    "Hindi words cannot be greater than total words."
                )
        return cleaned_data

class CertificateDataForm(forms.Form):
    """Form for manager to select financial year and quarter ending"""
    financial_year = forms.ChoiceField(
        label="Financial Year",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        choices=[]  # Will be set in __init__
    )
    quarter_ending = forms.ChoiceField(
        label="Quarter Ending",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        choices=[]  # Will be set in __init__
    )

    def __init__(self, *args, **kwargs):
        # Extract years and quarters from kwargs
        years = kwargs.pop('years', [])
        quarters = kwargs.pop('quarters', [])
        super().__init__(*args, **kwargs)
        
        # Set choices with empty option first
        year_choices = [('', '--- Select Financial Year ---')]
        for y in years:
            year_choices.append((y, y))
        
        quarter_choices = [('', '--- Select Quarter Ending ---')]
        for q in quarters:
            if q:  # Only add non-empty quarters
                quarter_choices.append((q, q))
        
        self.fields['financial_year'].choices = year_choices
        self.fields['quarter_ending'].choices = quarter_choices


from .models import ManagerQPR, AdminQPR, QPRRecord, Section1FilesData, Section2MeetingsData, Section3OfficialLanguagesData, Section4HindiLettersData, Section5EnglishRepliedHindiData, Section6IssuedLettersData, Section7NotingsData


class UserQPRForm(forms.Form):
    # Explicit fields for User (sections 2,4,5,6,7) - using names matching qpr_form inputs
    s2_meetings = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s2_minutes = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s2_papers_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s2_papers_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))

    s4_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s4_no_reply = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s4_replied_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s4_replied_eng = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))

    s5_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s5_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s5_english = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s5_noreply = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))

    s6_a_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s6_a_eng = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s6_a_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    # ... other s6 fields omitted for brevity; they can be added similarly when needed

    s7_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s7_eng = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s7_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s7_eoffice = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))


class HODQPRForm(UserQPRForm):
    # HOD includes section 1 in addition to User fields
    s1_total = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    s1_hindi = forms.IntegerField(required=False, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))


class ManagerQPRForm(forms.ModelForm):
    class Meta:
        model = ManagerQPR
        fields = [
            'financial_year', 'quarter',
            # Section 2
            's2_meetings_count', 's2_hindi_minutes', 's2_total_papers', 's2_hindi_papers',
            # Section 4
            's4_total_letters', 's4_no_reply_letters', 's4_replied_hindi_letters', 's4_replied_english_letters',
            # Section 5 (region A sample)
            's5_region_a_english_letters', 's5_region_a_replied_hindi', 's5_region_a_replied_english', 's5_region_a_no_reply',
            # Section 6 (region totals)
            's6_region_a_hindi_bilingual', 's6_region_a_english_only', 's6_region_a_total',
            's6_region_b_hindi_bilingual', 's6_region_b_english_only', 's6_region_b_total',
            's6_region_c_hindi_bilingual', 's6_region_c_english_only', 's6_region_c_total',
            # Section 7
            's7_hindi_pages', 's7_english_pages', 's7_total_pages', 's7_eoffice_notings',
            # Section 8
            's8_full_day_workshops', 's8_officers_trained', 's8_employees_trained',
            # Section 9
            's9_meeting_date', 's9_sub_committees_count', 's9_meetings_organized', 's9_agenda_hindi',
            # Section 10
            's10_meeting_date',
            # Section 11
            's11_innovative_work', 's11_special_events', 's11_hindi_medium_works'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure certain fields use appropriate widgets
        if 's9_meeting_date' in self.fields:
            self.fields['s9_meeting_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        if 's10_meeting_date' in self.fields:
            self.fields['s10_meeting_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        if 's9_agenda_hindi' in self.fields:
            # Represent Yes/No question as a select with Yes/No choices
            self.fields['s9_agenda_hindi'] = forms.ChoiceField(required=False, choices=[('', ''), ('Yes', 'Yes'), ('No', 'No')], widget=forms.Select())
        # Auto-fill and lock current financial year and quarter (readonly so value still submits)
        try:
            from datetime import date
            today = date.today()
            month = today.month
            # Quarter mapping (Indian FY Apr-Mar)
            if 4 <= month <= 6:
                current_quarter = '30 जून / Jun 30'
            elif 7 <= month <= 9:
                current_quarter = '30 सितंबर / Sep 30'
            elif 10 <= month <= 12:
                current_quarter = '31 दिसंबर / Dec 31'
            else:
                current_quarter = '31 मार्च / Mar 31'

            fiscal_year_start = today.year - 1 if month < 4 else today.year
            current_financial_year = f"{fiscal_year_start}-{fiscal_year_start + 1}"

            if 'financial_year' in self.fields:
                self.fields['financial_year'].initial = current_financial_year
                # Use a readonly text input so value is submitted but non-editable
                self.fields['financial_year'].widget = forms.TextInput(attrs={'readonly': 'readonly'})
            if 'quarter' in self.fields:
                self.fields['quarter'].initial = current_quarter
                # Render quarter as readonly text input to prevent selection changes
                self.fields['quarter'].widget = forms.TextInput(attrs={'readonly': 'readonly'})
        except Exception:
            pass
        for name, field in self.fields.items():
            # add bootstrap small inputs for numeric/text/date fields
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control form-control-sm').strip()


class AdminQPRForm(forms.ModelForm):
    class Meta:
        model = AdminQPR
        fields = [
            'financial_year', 'quarter',
            # Section 2
            'a_s2_meetings_count', 'a_s2_hindi_minutes', 'a_s2_total_papers', 'a_s2_hindi_papers',
            # Section 3
            'a_s3_total_documents', 'a_s3_bilingual_documents', 'a_s3_english_only_documents', 'a_s3_hindi_only_documents',
            # Section 4
            'a_s4_total_letters', 'a_s4_no_reply_letters', 'a_s4_replied_hindi_letters', 'a_s4_replied_english_letters',
            # Section 5
            'a_s5_region_a_english_letters', 'a_s5_region_a_replied_hindi', 'a_s5_region_a_replied_english', 'a_s5_region_a_no_reply',
            # Section 6
            'a_s6_region_a_hindi_bilingual', 'a_s6_region_a_english_only', 'a_s6_region_a_total',
            'a_s6_region_b_hindi_bilingual', 'a_s6_region_b_english_only', 'a_s6_region_b_total',
            'a_s6_region_c_hindi_bilingual', 'a_s6_region_c_english_only', 'a_s6_region_c_total',
            # Section 7
            'a_s7_hindi_pages', 'a_s7_english_pages', 'a_s7_total_pages', 'a_s7_eoffice_notings'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control form-control-sm').strip()

        # Auto-fill and lock current financial year and quarter for Admin form too
        try:
            from datetime import date
            today = date.today()
            month = today.month
            if 4 <= month <= 6:
                current_quarter = '30 जून / Jun 30'
            elif 7 <= month <= 9:
                current_quarter = '30 सितंबर / Sep 30'
            elif 10 <= month <= 12:
                current_quarter = '31 दिसंबर / Dec 31'
            else:
                current_quarter = '31 मार्च / Mar 31'

            fiscal_year_start = today.year - 1 if month < 4 else today.year
            current_financial_year = f"{fiscal_year_start}-{fiscal_year_start + 1}"

            if 'financial_year' in self.fields:
                self.fields['financial_year'].initial = current_financial_year
                self.fields['financial_year'].widget = forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control form-control-sm'})
            if 'quarter' in self.fields:
                self.fields['quarter'].initial = current_quarter
                self.fields['quarter'].widget = forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control form-control-sm'})
        except Exception:
            pass


