from django import forms
from .models import KPI, Indicator, KPIBonus
from django.contrib.auth import get_user_model

User = get_user_model()


class KPICreateForm(forms.ModelForm):
    # Дополнительные поля для бонуса
    target_amount = forms.DecimalField(
        label="Целевая сумма бонуса (при 100%)",
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Например, 50000'})
    )
    threshold_min = forms.FloatField(
        label="Минимальный порог (%)",
        initial=80,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    threshold_max = forms.FloatField(
        label="Максимальный порог (%)",
        initial=125,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = KPI
        fields = [
            'name', 'period', 'target_type', 'department', 'employee',
            'position', 'is_template', 'for_month'
        ]
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
        # Если мы редактируем существующий KPI, подгружаем данные бонуса в поля формы
        if self.instance.pk and hasattr(self.instance, 'bonus_setup'):
            self.fields['target_amount'].initial = self.instance.bonus_setup.target_amount
            self.fields['threshold_min'].initial = self.instance.bonus_setup.threshold_min
            self.fields['threshold_max'].initial = self.instance.bonus_setup.threshold_max

        self.fields['is_template'].help_text = "Отметьте, если этот KPI должен быть образцом."
        self.fields['for_month'].help_text = "Для шаблонов можно оставить пустым."

    def save(self, commit=True):
        instance = super().save(commit)
        # Сохраняем или обновляем бонус при сохранении KPI
        KPIBonus.objects.update_or_create(
            kpi=instance,
            defaults={
                'target_amount': self.cleaned_data['target_amount'],
                'threshold_min': self.cleaned_data['threshold_min'],
                'threshold_max': self.cleaned_data['threshold_max'],
            }
        )
        return instance


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
                attrs={'class': 'form-control border-danger', 'step': '0.1', 'min': '0', 'max': '125'}),
            'fact_qualitative': forms.NumberInput(
                attrs={'class': 'form-control border-danger', 'step': '0.1', 'min': '0', 'max': '125'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем подсказки более понятными
        self.fields['fact_quantitative'].help_text = "Введите % выполнения количественной части (0-125%)"
        self.fields['fact_qualitative'].help_text = "Введите % выполнения качественной части (0-125%)"


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