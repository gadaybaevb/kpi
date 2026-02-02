from django import forms
from .models import Entity
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from datetime import datetime



class UploadFinanceForm(forms.Form):
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all(),
        label="Филиал",
        empty_label="---"
    )

    # Списки для выбора
    MONTHS = [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)]
    YEARS = [(y, y) for y in range(datetime.now().year - 2, datetime.now().year + 2)]

    month = forms.ChoiceField(choices=MONTHS, label="Месяц")
    year = forms.ChoiceField(choices=YEARS, label="Год")

    file_pnl = forms.FileField(label="Файл ОПУ", required=False)
    file_osv = forms.FileField(label="Файл ОСВ", required=False)

    # Скрытое поле для подтверждения перезаписи
    overwrite = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'  # Обязательно
        self.helper.layout = Layout(
            Row(
                Column('entity', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('month', css_class='form-group col-md-6 mb-3'),
                Column('year', css_class='form-group col-md-6 mb-3'),
            ),
            'file_pnl',
            'file_osv',
            # Вот эта строка создает кнопку:
            Submit('submit', 'Загрузить данные', css_class='btn btn-primary w-100 fw-bold mt-3')
        )