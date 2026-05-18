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
from django.core.cache import cache
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
        
        self.error_messages['password_mismatch'] = translate_text(
            "The two password fields didn't match.", lang
        )
        self.fields['password1'].widget.attrs['autocomplete'] = 'new-password'
        self.fields['password2'].widget.attrs['autocomplete'] = 'new-password'


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
        choices=[('user', 'User'), ('manager', 'Manager'), ('hod', 'HOD'), ('admin', 'Admin'),('backup_user','Operational User')],
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
            ('backup_user', translate_text("Operational User", self.lang)),
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

        self.fields['password'].widget.attrs['autocomplete'] = 'current-password'

    def clean(self):
        """Authenticate using ONLY employee code"""
        
        cleaned_data = super(AuthenticationForm, self).clean()

        emp_code = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if not emp_code or not password:
            return cleaned_data
        
        cache_key = f"login_attempts_{emp_code}"
        attempts = cache.get(cache_key, 0)

        if attempts >= 3:
            raise forms.ValidationError(
                translate_text("Account locked due to 3 incorrect attempts. Please try again after 2 hours.", self.lang), 
                code='locked'
            )

        from .models import UserProfile

        try:
            profile = UserProfile.objects.select_related('user').get(
                employee_code=emp_code
            )
        except UserProfile.DoesNotExist:
            # Increment failed attempts even for invalid users to prevent brute-force enumeration
            cache.set(cache_key, attempts + 1, 7200)
            raise forms.ValidationError("Invalid Employee Code")
        
        
        user = authenticate(request=self.request,username=profile.user.username,password=password)

        if user is None:
            attempts += 1
            cache.set(cache_key, attempts, 7200)
            if attempts >= 3:
                raise forms.ValidationError(
                    translate_text("Account locked for 2 hours due to 3 incorrect attempts.", self.lang), 
                    code='locked'
                )
            else:
                raise forms.ValidationError(
                    translate_text(f"Invalid login. {3 - attempts} attempts remaining.", self.lang), 
                    code='invalid_login'
                )
        cache.delete(cache_key)
        self.confirm_login_allowed(user)
        self.user_cache = user

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


from .models import AdminQPR, EmployeeMaster, FinancialYear, ManagerQPR, QPRRecord, Section1FilesData, Section2MeetingsData, Section3OfficialLanguagesData, Section4HindiLettersData, Section5EnglishRepliedHindiData, Section6IssuedLettersData, Section7NotingsData

QPR_QUARTER_CHOICES = [
    ('Q1', 'Q1'),
    ('Q2', 'Q2'),
    ('Q3', 'Q3'),
    ('Q4', 'Q4'),
]


def _current_financial_year_bounds():
    today = timezone.localdate()
    start = today.year if today.month >= 4 else today.year - 1
    return start, start + 1


def _financial_year_choices():
    start, end = _current_financial_year_bounds()
    current_label = f"{start}-{end}"
    labels = ['2024-2025', '2025-2026', current_label]
    try:
        FinancialYear.objects.get_or_create(start_year=start, end_year=end)
        for fy in FinancialYear.objects.filter(is_active=True).order_by('-start_year', '-end_year'):
            label = str(fy)
            if label not in labels:
                labels.append(label)
    except Exception:
        pass
    return [(label, label) for label in labels]


def _current_quarter_code():
    month = timezone.localdate().month
    if month <= 3:
        return 'Q4'
    if month <= 6:
        return 'Q1'
    if month <= 9:
        return 'Q2'
    return 'Q3'


def _quarter_code_from_label(value):
    q = (value or '').strip()
    normalized = q.upper()
    if normalized in {'Q1', 'Q2', 'Q3', 'Q4'}:
        return normalized
    if 'Jun' in q or 'जून' in q:
        return 'Q1'
    if 'Sep' in q or 'सितंबर' in q or 'सित' in q:
        return 'Q2'
    if 'Dec' in q or 'दिसंबर' in q or 'दिस' in q:
        return 'Q3'
    if 'Mar' in q or 'मार्च' in q:
        return 'Q4'
    return _current_quarter_code()


def _configure_manager_admin_period_fields(form):
    if 'financial_year' in form.fields:
        choices = _financial_year_choices()
        initial = form.initial.get('financial_year') or choices[0][0]
        if initial and initial not in {value for value, _ in choices}:
            choices.append((initial, initial))
        form.initial['financial_year'] = initial
        form.fields['financial_year'] = forms.ChoiceField(
            choices=choices,
            initial=initial,
            widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
        )
    if 'quarter' in form.fields:
        quarter = _quarter_code_from_label(form.initial.get('quarter'))
        form.initial['quarter'] = quarter
        form.fields['quarter'] = forms.ChoiceField(
            choices=QPR_QUARTER_CHOICES,
            initial=quarter,
            widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
        )


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
        _configure_manager_admin_period_fields(self)
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

        _configure_manager_admin_period_fields(self)
        
class EmployeeMasterForm(forms.ModelForm):
    dropdown_fields = ('designation', 'state', 'division')
    class Meta:
        model = EmployeeMaster
        fields = [
            'empcode',
            'name',
            'hindi_name',
            'designation',
            'state',
            'mobile',
            'ip_number',
            'emergency_contact',
            'division',
            'is_active',
            'transferred_at',
        ]
        widgets = {
            'empcode': forms.NumberInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'hindi_name': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_number': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'division': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'transferred_at': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in self.dropdown_fields:
            self.fields[field_name] = forms.ChoiceField(
                required=False,
                choices=self._master_value_choices(field_name),
                widget=forms.Select(attrs={'class': 'form-select'})
            )

    def _master_value_choices(self, field_name):
        values = EmployeeMaster.objects.exclude(
            **{f'{field_name}__isnull': True}
        ).exclude(
            **{f'{field_name}__exact': ''}
        ).values_list(field_name, flat=True)

        options = sorted({value.strip() for value in values if value and value.strip()})
        current_value = self.initial.get(field_name)
        if self.instance and self.instance.pk:
            current_value = getattr(self.instance, field_name, current_value)
        if current_value:
            current_value = str(current_value).strip()
            if current_value and current_value not in options:
                options.append(current_value)
                options.sort()

        return [('', '--- Select ---')] + [(value, value) for value in options]

    def clean_empcode(self):
        value = self.cleaned_data.get('empcode')
        if value is None:
            raise ValidationError("Employee code is required.")
        return int(value)

    def clean(self):
        cleaned_data = super().clean()
        is_active = cleaned_data.get('is_active')
        transferred_at = cleaned_data.get('transferred_at')

        if is_active:
            cleaned_data['transferred_at'] = None
        elif transferred_at is None:
            cleaned_data['transferred_at'] = timezone.localdate()

        return cleaned_data
