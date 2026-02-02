from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UploadFinanceForm
from django.db.models.functions import TruncMonth
from .services import process_pnl_file, process_osv_file
from .models import Entity, PnLData, TrialBalance, Category
from datetime import datetime
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from datetime import datetime, date
import json  # Важно для передачи данных в JS
from django.db.models import Sum
from django.contrib import messages
from django.db.models.functions import ExtractYear, ExtractMonth
from scipy import stats
import numpy as np
from django.contrib.auth.mixins import LoginRequiredMixin


@login_required
def upload_financial_data(request):
    if request.method == 'POST':
        form = UploadFinanceForm(request.POST, request.FILES)
        if form.is_valid():
            entity = form.cleaned_data['entity']
            # Собираем дату из новых полей month и year
            period = date(int(form.cleaned_data['year']), int(form.cleaned_data['month']), 1)
            overwrite = request.POST.get('overwrite') == 'True'

            # Проверяем, есть ли уже данные за этот период
            existing_pnl = PnLData.objects.filter(entity=entity, period=period).exists()
            # existing_osv = ВашаМодельОСВ.objects.filter(entity=entity, period=period).exists()

            if existing_pnl and not overwrite:
                # Если данные есть, но подтверждения нет — возвращаем форму с флагом
                return render(request, 'analytics/upload.html', {
                    'form': form,
                    'needs_confirm': True,
                    'entity_name': entity.name,
                    'period_label': period.strftime('%m.%Y')
                })

            # Если пользователь нажал "Да, перезаписать"
            if overwrite:
                PnLData.objects.filter(entity=entity, period=period).delete()
                # ВашаМодельОСВ.objects.filter(entity=entity, period=period).delete()
                # Теперь удаляем и ОСВ:
                TrialBalance.objects.filter(entity=entity, period=period).delete()
                messages.info(request, f"Старые данные за {period.strftime('%B %Y')} удалены.")

            # Загрузка ОПУ
            if 'file_pnl' in request.FILES:
                process_pnl_file(request.FILES['file_pnl'], entity, period)
                messages.success(request, f"ОПУ {entity.name} успешно загружен.")

            # Загрузка ОСВ
            if 'file_osv' in request.FILES:
                process_osv_file(request.FILES['file_osv'], entity, period)
                messages.success(request, f"ОСВ {entity.name} успешно загружена.")

            return redirect('upload_financial_data')
    else:
        form = UploadFinanceForm()

    return render(request, 'analytics/upload.html', {'form': form})


class EntityListView(LoginRequiredMixin, ListView):
    model = Entity
    template_name = 'analytics/entity_list.html'


class EntityCreateView(LoginRequiredMixin, CreateView):
    model = Entity
    fields = ['name', 'is_hq']
    template_name = 'analytics/entity_form.html'
    success_url = reverse_lazy('entity_list')


class EntityUpdateView(LoginRequiredMixin, UpdateView):
    model = Entity
    fields = ['name', 'is_hq']
    template_name = 'analytics/entity_form.html'
    success_url = reverse_lazy('entity_list')


class PnLDataListView(LoginRequiredMixin, ListView):
    model = PnLData
    template_name = 'analytics/pnl_list.html'

    def get_queryset(self):
        # Фильтруем по филиалу из GET-запроса, если он есть
        queryset = super().get_queryset()
        entity_id = self.request.GET.get('entity')
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        return queryset.select_related('entity', 'category')


class TrialBalanceListView(LoginRequiredMixin, ListView):
    model = TrialBalance
    template_name = 'analytics/osv_list.html'
    context_object_name = 'balances'

    def get_queryset(self):
        qs = super().get_queryset()
        entity_id = self.request.GET.get('entity')
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs.order_by('account_code')


@login_required
def branch_dashboard(request):
    entity_id = request.GET.get('entity')
    selected_period = request.GET.get('period')

    entities = Entity.objects.all()
    available_months = []

    # 1. Если филиал выбран, получаем все уникальные месяцы
    if entity_id and entity_id.isdigit():
        # Важно: TruncMonth превращает любую дату месяца в 1-е число этого месяца
        available_months = PnLData.objects.filter(entity_id=entity_id) \
            .annotate(month=TruncMonth('period')) \
            .values_list('month', flat=True) \
            .distinct() \
            .order_by('-month')

    context = {
        'entities': entities,
        'available_months': available_months,
        'selected_entity_id': int(entity_id) if (entity_id and entity_id.isdigit()) else None,
        'selected_period': selected_period,
        'data': None,
    }

    # 2. Сбор данных
    if entity_id and selected_period and selected_period != '':
        try:
            pnl_records = PnLData.objects.filter(
                entity_id=entity_id,
                period=selected_period
            ).select_related('category').order_by('category__order')

            report_data = []
            labels = []
            fact_values = []
            plan_values = []

            for item in pnl_records:
                diff = item.fact - item.plan
                perc = (item.fact / item.plan * 100) if item.plan != 0 else 0

                report_data.append({
                    'category': item.category.name,
                    'is_total': item.category.is_total,
                    'plan': float(item.plan),
                    'fact': float(item.fact),
                    'diff': float(diff),
                    'perc': float(perc),
                })

                # В график берем только основные статьи (не итоги) для ясности
                if not item.category.is_total and (item.fact != 0 or item.plan != 0):
                    labels.append(item.category.name[:20] + '...') # Обрезаем длинные имена
                    fact_values.append(float(item.fact))
                    plan_values.append(float(item.plan))

            context.update({
                'data': report_data,
                'chart_labels': json.dumps(labels),
                'chart_fact': json.dumps(fact_values),
                'chart_plan': json.dumps(plan_values),
            })
        except Exception as e:
            print(f"Error: {e}")

    return render(request, 'analytics/branch_dashboard.html', context)


@login_required
def consolidated_report(request):
    selected_period = request.GET.get('period')
    entities = Entity.objects.all()

    # 1. Получаем список только тех месяцев, за которые реально есть данные в базе
    available_months = PnLData.objects.annotate(
        month=TruncMonth('period')
    ).values_list('month', flat=True).distinct().order_by('-month')

    matrix = {}
    total_network = {}  # Для хранения суммы по всей сети

    if selected_period:
        categories = Category.objects.all().order_by('order')
        # Получаем все данные за период одним запросом для скорости
        pnl_data = PnLData.objects.filter(period=selected_period).select_related('category', 'entity')

        for cat in categories:
            matrix[cat] = {}  # Используем объект категории как ключ
            row_total = 0

            for ent in entities:
                # Фильтруем данные в памяти (Python быстрее, чем 100 запросов к БД)
                val = next((item.fact for item in pnl_data if item.category_id == cat.id and item.entity_id == ent.id),
                           0)
                matrix[cat][ent.id] = val
                row_total += val

            total_network[cat.id] = row_total

    return render(request, 'analytics/consolidated.html', {
        'matrix': matrix,
        'entities': entities,
        'available_months': available_months,
        'selected_period': selected_period,
        'total_network': total_network
    })


@login_required
def analytics_index(request):
    """Главная страница модуля аналитики"""
    return render(request, 'analytics/index.html')


@login_required
def upload_audit_calendar(request):
    # 1. Получаем выбранный год из GET-запроса, по умолчанию - текущий
    current_year = datetime.now().year
    year = request.GET.get('year')
    year = int(year) if year and year.isdigit() else current_year

    # 2. Собираем все уникальные годы из обеих таблиц для селекта
    years_pnl = PnLData.objects.annotate(y=ExtractYear('period')).values_list('y', flat=True)
    years_osv = TrialBalance.objects.annotate(y=ExtractYear('period')).values_list('y', flat=True)

    # Объединяем, убираем дубликаты и сортируем
    available_years = sorted(list(set(list(years_pnl) + list(years_osv) + [current_year])), reverse=True)

    entities = Entity.objects.all()
    months = range(1, 13)

    audit_data = []
    for entity in entities:
        entity_months = []
        for month in months:
            # Проверяем наличие ОПУ и ОСВ за конкретный год и месяц
            has_pnl = PnLData.objects.filter(entity=entity, period__year=year, period__month=month).exists()
            has_osv = TrialBalance.objects.filter(entity=entity, period__year=year, period__month=month).exists()

            entity_months.append({
                'month': month,
                'has_pnl': has_pnl,
                'has_osv': has_osv,
            })
        audit_data.append({
            'entity': entity,
            'months': entity_months
        })

    return render(request, 'analytics/upload_audit.html', {
        'audit_data': audit_data,
        'year': year,
        'available_years': available_years,  # Список годов для выпадающего списка
        'month_names': ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    })


@login_required
def consolidated_osv(request):
    selected_period = request.GET.get('period')
    entities = Entity.objects.all()

    # Список периодов, где есть данные ОСВ (для селектора)
    available_months = TrialBalance.objects.annotate(
        month=TruncMonth('period')
    ).values_list('month', flat=True).distinct().order_by('-month')

    matrix = {}

    if selected_period:
        # 1. Получаем все данные за период одним запросом
        osv_qs = TrialBalance.objects.filter(period=selected_period).select_related('entity')

        # 2. Составляем список уникальных счетов, которые есть в этом месяце (код + имя)
        # Используем dict, чтобы сохранить соответствие кода и названия
        accounts_map = {obj.account_code: obj.account_name for obj in osv_qs}
        sorted_account_codes = sorted(accounts_map.keys())

        # 3. Строим матрицу
        for code in sorted_account_codes:
            name = accounts_map[code]
            matrix[code] = {
                'name': name,
                'branches': {},
                'total_debit': 0,
                'total_credit': 0
            }

            for ent in entities:
                # Ищем запись для конкретного филиала и счета
                # Используем генератор списка для фильтрации в памяти (быстрее запросов)
                record = next((item for item in osv_qs if item.account_code == code and item.entity_id == ent.id), None)

                if record:
                    debit = float(record.debit_turnover)
                    credit = float(record.credit_turnover)
                    matrix[code]['branches'][ent.id] = {'d': debit, 'c': credit}
                    matrix[code]['total_debit'] += debit
                    matrix[code]['total_credit'] += credit
                else:
                    matrix[code]['branches'][ent.id] = {'d': 0, 'c': 0}

    return render(request, 'analytics/consolidated_osv.html', {
        'matrix': matrix,
        'entities': entities,
        'available_months': available_months,
        'selected_period': selected_period,
    })


@login_required
def annual_analytics(request):
    selected_years = request.GET.getlist('years')
    if not selected_years:
        selected_years = [str(date.today().year)]
    selected_years = [int(y) for y in selected_years]

    entity_id = request.GET.get('entity')
    available_years = range(2023, date.today().year + 2)
    entities = Entity.objects.all()
    months = range(1, 13)

    # КОРРЕКТИРОВКА: Имена должны строго совпадать или быть частью имен в БД
    # Используем технический ключ для маппинга, чтобы в коде было удобно
    categories_map = {
        "ИТОГО ПРОДАЖИ": "ИТОГО ПРОДАЖИ",
        "ЧИСТАЯ ПРИБЫЛЬ": "ЧИСТАЯ ПРИБЫЛЬ",
        "КОЛИЧЕСТВО СЛУШАТЕЛЕЙ": "Кол-во заявок на обучение / Number of enrolled students"
    }

    target_categories = list(categories_map.keys())

    # 1. Вычисляем сезонные коэффициенты
    seasonality_map = {cat: {m: 0.0 for m in months} for cat in target_categories}
    historical_data = PnLData.objects.all()
    if entity_id:
        historical_data = historical_data.filter(entity_id=entity_id)

    for cat_key, db_name in categories_map.items():
        month_averages = []
        for m in months:
            val = historical_data.filter(
                period__month=m,
                category__name__icontains=db_name
            ).aggregate(total=Sum('fact'))['total'] or 0
            seasonality_map[cat_key][m] = float(val)
            month_averages.append(float(val))

        # Нормализация
        mean_val = np.mean(month_averages) if np.mean(month_averages) > 0 else 1
        for m in months:
            seasonality_map[cat_key][m] = seasonality_map[cat_key][m] / mean_val

    # 2. Формирование данных для графиков
    comparison_data = {}
    for year in selected_years:
        comparison_data[year] = {cat: {'fact': [], 'forecast': []} for cat in target_categories}

        for cat_key, db_name in categories_map.items():
            monthly_facts = []
            for m in months:
                period = date(year, m, 1)
                qs = PnLData.objects.filter(period=period, category__name__icontains=db_name)
                if entity_id:
                    qs = qs.filter(entity_id=entity_id)

                val = qs.aggregate(total=Sum('fact'))['total'] or 0
                monthly_facts.append(float(val))

            comparison_data[year][cat_key]['fact'] = monthly_facts

            # ПРОГНОЗ
            y_history = [v for v in monthly_facts if v > 0]
            if 0 < len(y_history) < 12:
                current_avg = np.mean(y_history)
                forecast_values = []
                for m in months:
                    if m <= len(y_history):
                        forecast_values.append(monthly_facts[m - 1])
                    else:
                        coeff = seasonality_map[cat_key][m]
                        prediction = current_avg * coeff
                        forecast_values.append(round(max(0, prediction), 2))
                comparison_data[year][cat_key]['forecast'] = forecast_values
            else:
                comparison_data[year][cat_key]['forecast'] = monthly_facts

    return render(request, 'analytics/annual_report.html', {
        'selected_years': selected_years,
        'available_years': available_years,
        'entities': entities,
        'selected_entity_id': int(entity_id) if (entity_id and entity_id.isdigit()) else None,
        'comparison_data_json': json.dumps(comparison_data),
        'months_labels': json.dumps(
            ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"])
    })