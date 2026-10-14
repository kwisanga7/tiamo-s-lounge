from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from .models import Event, LoungePost, StaffMember, StaffShift, StaffTask, SupportRequest, Ticket, UserProfile

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


class UserProfileForm(forms.ModelForm):
    profile_picture = forms.ImageField(required=False, label="Profile picture")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        if self.instance and self.instance.pk:
            self.fields["profile_picture"].initial = self.instance.profile.profile_picture

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        duplicate = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def clean_profile_picture(self):
        picture = self.cleaned_data.get("profile_picture")
        if picture and picture is not False and picture.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose a profile picture smaller than 5 MB.")
        return picture

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            picture = self.cleaned_data.get("profile_picture")
            if picture is False:
                profile.profile_picture.delete(save=False)
                profile.profile_picture = None
                profile.save(update_fields=["profile_picture"])
            elif picture:
                previous_name = profile.profile_picture.name
                profile.profile_picture = picture
                profile.save(update_fields=["profile_picture"])
                if previous_name and previous_name != profile.profile_picture.name:
                    profile.profile_picture.storage.delete(previous_name)
        return user


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
        if self.instance and self.instance.pk:
            self.fields.pop("password1", None)
            self.fields.pop("password2", None)
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
        fields = ["title", "description", "starts_at", "venue", "image", "ticket_price", "capacity", "published"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 5 MB.")
        return image


class StaffForm(forms.ModelForm):
    class Meta:
        model = StaffMember
        fields = ["name", "email", "phone", "role", "active"]


class StaffTaskForm(forms.ModelForm):
    due_at = forms.DateTimeField(required=False, widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}), input_formats=["%Y-%m-%dT%H:%M"])

    class Meta:
        model = StaffTask
        fields = ["title", "details", "assigned_to", "event", "due_at"]
        widgets = {"details": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = StaffMember.objects.filter(active=True)
        self.fields["event"].queryset = Event.objects.order_by("-starts_at")
        self.fields["event"].required = False


class StaffShiftForm(forms.ModelForm):
    starts_at = forms.DateTimeField(widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}), input_formats=["%Y-%m-%dT%H:%M"])
    ends_at = forms.DateTimeField(widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}), input_formats=["%Y-%m-%dT%H:%M"])

    class Meta:
        model = StaffShift
        fields = ["staff_member", "event", "starts_at", "ends_at", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff_member"].queryset = StaffMember.objects.filter(active=True)
        self.fields["event"].queryset = Event.objects.order_by("-starts_at")
        self.fields["event"].required = False

    def clean(self):
        cleaned = super().clean()
        starts_at, ends_at = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "Shift end time must be after the start time.")
        return cleaned


class TicketPurchaseForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["buyer_name", "buyer_email"]


class SupportRequestForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ["subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


class LoungePostForm(forms.ModelForm):
    class Meta:
        model = LoungePost
        fields = ["title", "message", "image", "video", "notify_role"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "Write an update for the Tiamo's Lounge community..."}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "video": forms.ClearableFileInput(attrs={"accept": "video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 5 MB.")
        return image

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if video:
            if video.size > 30 * 1024 * 1024:
                raise forms.ValidationError("Choose a video smaller than 30 MB.")
            if video.name.rsplit(".", 1)[-1].lower() not in {"mp4", "webm", "mov"}:
                raise forms.ValidationError("Use an MP4, WebM, or MOV video.")
        return video

