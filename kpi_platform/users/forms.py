from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'department', 'position')


class UserUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем логин доступным только для чтения, чтобы не сломать систему
        self.fields['username'].widget.attrs['readonly'] = True
        # Можно также добавить стили для визуального отличия
        self.fields['username'].widget.attrs['class'] = 'form-control-plaintext fw-bold'

    class Meta:
        model = User
        # Добавляем 'username' в начало списка полей
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'department', 'position', 'superior', 'is_active')
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            # Добавьте стили для остальных полей, чтобы они выглядели одинаково
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }