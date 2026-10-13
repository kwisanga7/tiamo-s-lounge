from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from .models import Event, StaffMember, Ticket, UserProfile

User = get_user_model()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please sign in instead.")
        return email


class UserAccountForm(forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.Role.choices)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            profile, _ = UserProfile.objects.get_or_create(
                user=self.instance,
                defaults={"role": UserProfile.Role.ADMIN if self.instance.is_superuser else UserProfile.Role.USER},
            )
            self.fields["role"].initial = UserProfile.Role.ADMIN if self.instance.is_superuser else profile.role
            if self.instance.is_superuser:
                self.fields["role"].disabled = True
        else:
            self.fields["role"].initial = UserProfile.Role.USER
        self.fields["email"].required = True
        self.fields["is_active"].label = "Account active"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        duplicate = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if not self.instance.pk and not password1:
            self.add_error("password1", "Set a password for this account.")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "The passwords do not match.")
            elif password1:
                try:
                    validate_password(password1, self.instance)
                except forms.ValidationError as error:
                    self.add_error("password1", error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data["role"]
        password = self.cleaned_data.get("password1")
        user.is_staff = user.is_superuser or role != UserProfile.Role.USER
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save()
            self.save_m2m()
        return user


class EventForm(forms.ModelForm):
    starts_at = forms.DateTimeField(widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}), input_formats=["%Y-%m-%dT%H:%M"])

    class Meta:
        model = Event
        fields = ["title", "description", "starts_at", "venue", "ticket_price", "capacity", "published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class StaffForm(forms.ModelForm):
    class Meta:
        model = StaffMember
        fields = ["name", "email", "phone", "role", "active"]


class TicketPurchaseForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["buyer_name", "buyer_email"]

