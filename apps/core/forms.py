from django import forms

from .models import ContactMessage


class ContactInquiryForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ('name', 'email', 'subject', 'message')
