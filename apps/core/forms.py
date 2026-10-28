from django import forms

from .models import ContactMessage
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class TravelerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, max_length=254)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'password1', 'password2')


class ContactInquiryForm(forms.ModelForm):
    destination_country = forms.ChoiceField(required=False, label='Destination')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Country
        self.fields['destination_country'].choices = [('', 'General enquiry')] + list(
            Country.objects.filter(is_active=True).values_list('slug', 'name'))

    class Meta:
        model = ContactMessage
        fields = ('name', 'email', 'subject', 'message')
