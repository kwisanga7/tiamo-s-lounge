from django import forms
from .models import Event, StaffMember, Ticket


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

