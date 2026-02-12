from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser
from .templatetags.translate_tags import translate_text
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
import hashlib
from captcha.fields import CaptchaField

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    #captcha = CaptchaField()
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
        full_label = mark_safe(f'{consent_text} <a href="{policy_url}" target="_blank">{link_text}</a>')
        self.fields['consent'].label = full_label
        self.fields['username'].help_text = ""
        self.fields['password1'].help_text = ""
        self.fields['password2'].help_text = translate_text("Enter the same password as before, for verification.", lang)
        self.fields['username'].label = translate_text("Username", lang)
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

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username.isdigit():
            raise forms.ValidationError(translate_text("Username must contain only integers.", self.lang))
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email').lower().strip()
        email_hash = hashlib.sha256(email.encode()).hexdigest()
        # Check if email is already in the database
        if CustomUser.objects.filter(email_hash=email_hash).exists():
            error_msg = translate_text("A user with this email already exists.", self.lang)
            raise forms.ValidationError(error_msg)
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
        choices=[('user', 'User'), ('manager', 'Manager'), ('admin', 'Admin'),('backup_user','Backup User')],
        widget=forms.Select(attrs={'class': 'form-select'})
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
        
        self.fields["username"].label = translate_text("Username", self.lang)
        self.fields["password"].label = translate_text("Password", self.lang)
        self.fields['role'].label = translate_text("Select Role", self.lang)
        self.fields['captcha'].label = translate_text("Enter the characters shown", self.lang)
        
        self.error_messages['invalid_login'] = translate_text(
            "Please enter a correct username and password. Note that both fields may be case-sensitive.",
            self.lang
        )
        self.error_messages['inactive'] = translate_text("This account is inactive.", self.lang)
        
        self.fields['role'].choices = [
            ('user', translate_text("User", self.lang)),
            ('manager', translate_text("Manager", self.lang)),
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

