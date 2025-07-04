from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class UserRegisterForm(UserCreationForm):
    display_name = forms.CharField(max_length=100, required=True, help_text='用於在遊戲中顯示的名稱')

    class Meta:
        model = User
        fields = ['username', 'display_name', 'password1', 'password2']
