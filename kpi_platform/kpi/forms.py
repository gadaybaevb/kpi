from django import forms
from .models import KPI, Indicator
from django.contrib.auth import get_user_model

User = get_user_model()


class KPICreateForm(forms.ModelForm):
    class Meta:
        model = KPI
        # Добавили is_template и for_month
        fields = ['name', 'period', 'target_type', 'department', 'employee', 'position', 'is_template', 'for_month']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'period': forms.Select(attrs={'class': 'form-select'}),
            'target_type': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-control'}),
            'is_template': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'for_month': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'is_template'].help_text = "Отметьте, если этот KPI должен быть образцом для генерации каждый месяц."
        self.fields['for_month'].help_text = "Для обычных KPI укажите месяц. Для шаблонов можно оставить пустым."


class IndicatorCreateForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = [
            'name', 'weight', 'indicator_type',
            'desc_quantitative', 'desc_qualitative',
            'threshold_min', 'threshold_max', 'plan_value'
        ]
        # Виджеты оставляем как есть, они у тебя отличные
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название индикатора'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '100'}),
            'indicator_type': forms.Select(attrs={'class': 'form-select'}),
            'desc_quantitative': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'desc_qualitative': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'threshold_min': forms.NumberInput(attrs={'class': 'form-control'}),
            'threshold_max': forms.NumberInput(attrs={'class': 'form-control'}),
            'plan_value': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class IndicatorUpdateFactForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = ['fact_quantitative', 'fact_qualitative']
        widgets = {
            # Ограничиваем ввод до 120% согласно твоим требованиям
            'fact_quantitative': forms.NumberInput(
                attrs={'class': 'form-control border-danger', 'step': '0.1', 'min': '0', 'max': '120'}),
            'fact_qualitative': forms.NumberInput(
                attrs={'class': 'form-control border-danger', 'step': '0.1', 'min': '0', 'max': '120'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем подсказки более понятными
        self.fields['fact_quantitative'].help_text = "Введите % выполнения количественной части (0-120%)"
        self.fields['fact_qualitative'].help_text = "Введите % выполнения качественной части (0-120%)"


class IndicatorRejectForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = ['rejection_reason'] # Не забудь добавить это поле в модель Indicator
        widgets = {
            'rejection_reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Укажите причину отклонения...'
            }),
        }