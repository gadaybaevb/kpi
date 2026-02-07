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
import pandas as pd
from datetime import datetime, date
import json  # Важно для передачи данных в JS
from django.db.models import Sum, Q
from django.contrib import messages
from django.db.models.functions import ExtractYear, ExtractMonth
import numpy as np
from django.contrib.auth.mixins import LoginRequiredMixin
import re
from django.db import transaction


# Словарик для перевода русских месяцев в числа
RUS_MONTHS = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'июн': 6,
    'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
}


def process_multi_pnl_file(file, entity, year):
    df = pd.read_excel(file, header=None)

    # 1. Поиск шапки
    header_idx = None
    for i, row in df.iterrows():
        row_str = " ".join([str(x).lower() for x in row.values])
        if 'факт' in row_str and 'план' in row_str:
            header_idx = i
            break

    if header_idx is None:
        return 0

    # 2. Определение колонок месяцев
    months_row = df.iloc[header_idx - 1]
    columns_row = df.iloc[header_idx]
    month_configs = []
    current_m = None

    for col_idx in range(len(columns_row)):
        cell_m = str(months_row.iloc[col_idx]).lower().strip()
        for m_name, m_num in RUS_MONTHS.items():
            if m_name in cell_m:
                current_m = m_num

        col_name = str(columns_row.iloc[col_idx]).lower().strip()
        if col_name == 'факт' and current_m:
            if 'итого' not in str(months_row.iloc[col_idx]).lower():
                month_configs.append({'month': current_m, 'f': col_idx, 'p': col_idx + 1})

    # 3. Сбор и сохранение данных
    with transaction.atomic():
        # Удаляем старое за эти месяцы
        target_months = [cfg['month'] for cfg in month_configs]
        PnLData.objects.filter(entity=entity, period__year=year, period__month__in=target_months).delete()

        data_rows = df.iloc[header_idx + 1:]
        to_create = []

        def force_float(val):
            if pd.isna(val): return 0.0
            s = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
            s = re.sub(r'[^\d\.\-]', '', s)
            try:
                return float(s) if s else 0.0
            except:
                return 0.0

        for i, row in data_rows.iterrows():
            # Название статьи из Excel
            c1 = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ""
            c0 = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
            cat_name_text = c1 if (c1 and c1.lower() != 'nan') else c0

            if not cat_name_text or cat_name_text.lower() in ['nan', 'итого', 'total', 'факт', 'план']:
                continue

            # --- КЛЮЧЕВОЙ МОМЕНТ: Находим объект Category в базе ---
            # get_or_create вернет объект, если он есть, или создаст новый
            category_obj, created = Category.objects.get_or_create(name=cat_name_text)

            for cfg in month_configs:
                f_val = force_float(row.iloc[cfg['f']])
                p_val = force_float(row.iloc[cfg['p']])

                if f_val == 0 and p_val == 0:
                    continue

                to_create.append(PnLData(
                    entity=entity,
                    period=date(year, cfg['month'], 1),
                    category=category_obj,  # Передаем ОБЪЕКТ, а не строку
                    fact=f_val,
                    plan=p_val
                ))

        if to_create:
            PnLData.objects.bulk_create(to_create)
            print(f"УСПЕХ: Записано {len(to_create)} строк!")
        else:
            print("ВНИМАНИЕ: Данные не собраны.")

    return len(target_months)


@login_required
def validate_file_type(file, expected_type):
    try:
        # Читаем первые 30 строк без заголовков
        df = pd.read_excel(file, nrows=30, header=None)

        # Превращаем в список строк, убирая пустые значения (nan)
        flat_list = df.astype(str).values.flatten()
        all_text = " ".join([str(x) for x in flat_list if str(x).lower() != 'nan']).lower()

        # Убираем лишние пробелы и переносы
        all_text = re.sub(r'\s+', ' ', all_text)

        if expected_type == 'osv':
            # В ОСВ обязательно должны быть эти 3 слова
            if 'оборотно-сальдовая' not in all_text or 'счет' not in all_text:
                return False, "Файл не распознан как ОСВ (не найдена шапка ведомости)."

            # Проверка наличия колонок
            if 'дебет' not in all_text and 'кредит' not in all_text:
                return False, "В ОСВ не найдены колонки Дебет/Кредит."

        elif expected_type == 'pnl':
            # В ОПУ ищем характерные слова из вашего файла
            # Проверяем по отдельности, так как они могут быть в разных ячейках
            pnl_markers = ['сравнительный', 'анализ', 'фхд']
            if not all(m in all_text for m in pnl_markers):
                return False, "Файл не похож на ОПУ (не найдено 'Сравнительный анализ ФХД')."

            # В вашем ОПУ 'план' и 'факт' — железные маркеры
            if 'план' not in all_text or 'факт' not in all_text:
                return False, "В ОПУ не найдены обязательные столбцы План/Факт."

            # Защита от перепутывания
            if 'оборотно-сальдовая' in all_text:
                return False, "Это файл ОСВ, а вы загружаете его в поле ОПУ."

        return True, ""
    except Exception as e:
        return False, f"Ошибка парсинга: {str(e)}"


@login_required
def upload_financial_data(request):
    if request.method == 'POST':
        form = UploadFinanceForm(request.POST, request.FILES)
        is_multi_month = request.POST.get('multi_month') == 'on'

        if form.is_valid():
            entity = form.cleaned_data['entity']
            year = int(form.cleaned_data['year'])
            month_val = form.cleaned_data.get('month')
            overwrite = request.POST.get('overwrite') == 'True'

            if not is_multi_month and not month_val:
                messages.error(request, "Выберите месяц для одиночной загрузки.")
                return render(request, 'analytics/upload.html', {'form': form})

            # Обработка ОПУ
            if 'file_pnl' in request.FILES:
                f_pnl = request.FILES['file_pnl']
                try:
                    if is_multi_month:
                        count = process_multi_pnl_file(f_pnl, entity, year)
                        messages.success(request, f"Успешно загружено месяцев: {count}")
                    else:
                        period = date(year, int(month_val), 1)
                        if overwrite:
                            PnLData.objects.filter(entity=entity, period=period).delete()
                        # Убедитесь, что внутри process_pnl_file тоже используются поля category, fact, plan
                        process_pnl_file(f_pnl, entity, period)
                        messages.success(request, f"ОПУ загружен за {month_val}.{year}")
                except Exception as e:
                    messages.error(request, f"Ошибка ОПУ: {str(e)}")

            # Обработка ОСВ
            if 'file_osv' in request.FILES:
                period = date(year, int(month_val), 1) if month_val else None
                if period:
                    if overwrite:
                        TrialBalance.objects.filter(entity=entity, period=period).delete()
                    process_osv_file(request.FILES['file_osv'], entity, period)
                    messages.success(request, f"ОСВ загружена.")

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
    # 1. Получаем параметры из запроса
    selected_years = request.GET.getlist('years')
    if not selected_years:
        # По умолчанию показываем текущий год
        selected_years = [str(date.today().year)]
    selected_years = [int(y) for y in selected_years]

    entity_id = request.GET.get('entity')
    # Доступные годы для фильтра (от 2023 до следующего)
    available_years = range(2023, date.today().year + 2)
    entities = Entity.objects.all()
    months = range(1, 13)

    # Словарь сопоставления (Ключ для кода : Имя в базе данных)
    categories_map = {
        "ИТОГО ПРОДАЖИ": "ИТОГО ПРОДАЖИ",
        "ЧИСТАЯ ПРИБЫЛЬ": "ЧИСТАЯ ПРИБЫЛЬ",
        "КОЛИЧЕСТВО СЛУШАТЕЛЕЙ": "Кол-во заявок на обучение / Number of enrolled students"
    }

    target_categories = list(categories_map.keys())

    # Базовый QuerySet с учетом выбранного филиала
    historical_data = PnLData.objects.all()
    if entity_id:
        historical_data = historical_data.filter(entity_id=entity_id)

    # --- ШАГ 1: РАСЧЕТ СЕЗОННОСТИ И БАЗОВОГО ТРЕНДА ---
    seasonality_map = {}
    global_trends = {}

    for cat_key, db_name in categories_map.items():
        # Собираем данные по месяцам за все время для профиля сезонности
        m_vals = []
        for m in months:
            val = historical_data.filter(
                period__month=m,
                category__name__icontains=db_name
            ).aggregate(total=Sum('fact'))['total'] or 0
            m_vals.append(float(val))

        # Считаем коэффициенты (отклонение каждого месяца от среднего)
        total_mean = np.mean(m_vals) if np.mean(m_vals) != 0 else 1
        seasonality_map[cat_key] = [v / total_mean for v in m_vals]

        # База для прогноза: Среднемесячный факт за прошлый год (2025)
        # Это исключает занижение из-за слабых старых данных
        last_year = date.today().year - 1
        last_year_avg = historical_data.filter(
            category__name__icontains=db_name,
            period__year=last_year
        ).aggregate(avg=Sum('fact'))['avg']

        if last_year_avg:
            global_trends[cat_key] = float(last_year_avg) / 12
        else:
            # Если 2025 пуст, берем последние 3 доступных месяца в базе
            fallback = historical_data.filter(
                category__name__icontains=db_name
            ).exclude(fact=0).order_by('-period')[:3]
            global_trends[cat_key] = np.mean([float(x.fact) for x in fallback]) if fallback.exists() else 0

    # --- ШАГ 2: ФОРМИРОВАНИЕ ДАННЫХ ДЛЯ ВЫВОДА ---
    comparison_data = {}
    for year in selected_years:
        # Структура: факт, план и прогноз для каждой категории
        comparison_data[year] = {
            cat: {'fact': [], 'plan': [], 'forecast': []} for cat in target_categories
        }

        for cat_key, db_name in categories_map.items():
            monthly_facts = []
            monthly_plans = []

            for m in months:
                p = date(year, m, 1)
                res = historical_data.filter(
                    period=p,
                    category__name__icontains=db_name
                ).aggregate(f_sum=Sum('fact'), p_sum=Sum('plan'))

                monthly_facts.append(float(res['f_sum'] or 0))
                monthly_plans.append(float(res['p_sum'] or 0))

            comparison_data[year][cat_key]['fact'] = monthly_facts
            comparison_data[year][cat_key]['plan'] = monthly_plans

            # Расчет текущей базы (current_avg) для этого года
            y_history = [v for v in monthly_facts if v != 0]

            if len(y_history) > 0:
                # Если в году уже есть данные, берем их среднее (актуальный тренд)
                if cat_key == "ЧИСТАЯ ПРИБЫЛЬ":
                    current_avg = np.mean(y_history[-6:]) if len(y_history) >= 6 else np.mean(y_history)
                else:
                    current_avg = np.mean(y_history[-2:])
            else:
                # Если год пустой (будущий), берем нашу "планку" из 2025 года
                current_avg = global_trends.get(cat_key, 0)

            # Защита от NaN при пустых расчетах
            if np.isnan(current_avg): current_avg = 0

            # Генерация прогнозной линии
            forecast_values = []
            for m in months:
                # Если уже есть реальный факт за месяц, прогноз совпадает с ним
                if monthly_facts[m - 1] != 0:
                    forecast_values.append(monthly_facts[m - 1])
                else:
                    # Умножаем актуальный тренд на коэффициент сезонности месяца
                    coeff = seasonality_map[cat_key][m - 1]
                    val = round(current_avg * coeff, 2)

                    # Запрещаем отрицательные продажи и количество студентов
                    if cat_key != "ЧИСТАЯ ПРИБЫЛЬ":
                        val = max(0, val)
                    forecast_values.append(val)

            comparison_data[year][cat_key]['forecast'] = forecast_values

    # 3. Рендеринг страницы
    context = {
        'selected_years': selected_years,
        'available_years': available_years,
        'entities': entities,
        'selected_entity_id': int(entity_id) if (entity_id and entity_id.isdigit()) else None,
        'comparison_data_json': json.dumps(comparison_data),
        'months_labels': json.dumps(
            ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
        )
    }
    return render(request, 'analytics/annual_report.html', context)


@login_required
def cash_flow_analytics(request):
    selected_years = request.GET.getlist('years')
    if not selected_years:
        selected_years = [str(date.today().year)]
    selected_years = [int(y) for y in selected_years]

    entity_id = request.GET.get('entity')
    is_consolidated = not entity_id

    available_years = range(2023, date.today().year + 2)
    entities = Entity.objects.all()
    months = range(1, 13)

    # Категории анализа
    cash_categories = {
        "TOTAL_IN": {"code": "1.0", "field": "debit_turnover"},
        "TOTAL_OUT": {"code": "1.0", "field": "credit_turnover"},
        "BANK_IN": {"code": "1.02", "field": "debit_turnover"},
        "CASH_10_IN": {"code": "1.01.10", "field": "debit_turnover"},
        "CASH_11_IN": {"code": "1.01.11", "field": "debit_turnover"},
    }

    def get_filtered_qs(base_qs, cfg_code, field_name):
        """
        Исключает субтоталы, счета выше 1.02.* и внутригрупповые обороты ГО.
        """
        # 1. Берем только счета, начинающиеся на 1.01 или 1.02
        # 2. И только те, у которых есть 2 точки (листовые счета), исключая 1.01 и 1.02
        qs = base_qs.filter(
            Q(account_code__startswith="1.01.") | Q(account_code__startswith="1.02."),
            account_code__regex=r'^\d+\.\d+\.\d+'
        )

        # Если мы считаем конкретную категорию (например, CASH_10_IN),
        # дополнительно фильтруем по её префиксу
        if cfg_code != "1.0":
            qs = qs.filter(account_code__startswith=cfg_code)

        if is_consolidated:
            # Исключаем технические переводы ГО
            qs = qs.exclude(entity__is_hq=True, account_code__in=['1.01.30', '1.01.50'])

            # У счета 1.02.10 (Банк) у ГО исключаем расход при консолидации
            if field_name == 'credit_turnover':
                qs = qs.exclude(entity__is_hq=True, account_code='1.02.10')

        return qs

    # 1. Расчет сезонности и трендов
    seasonality_map = {}
    last_trends = {}

    for key, cfg in cash_categories.items():
        m_vals = []
        for m in months:
            qs = TrialBalance.objects.filter(period__month=m)
            if entity_id: qs = qs.filter(entity_id=entity_id)
            final_qs = get_filtered_qs(qs, cfg['code'], cfg['field'])
            val = float(final_qs.aggregate(total=Sum(cfg['field']))['total'] or 0)
            m_vals.append(val)

        avg_val = np.mean(m_vals) if np.mean(m_vals) > 0 else 1
        seasonality_map[key] = [v / avg_val for v in m_vals]

        trend_qs = TrialBalance.objects.all()
        if entity_id: trend_qs = trend_qs.filter(entity_id=entity_id)
        final_trend_qs = get_filtered_qs(trend_qs, cfg['code'], cfg['field'])
        trend_data = final_trend_qs.values('period').annotate(total=Sum(cfg['field'])).order_by('-period')[:2]
        last_trends[key] = np.mean([float(x['total']) for x in trend_data]) if trend_data else 0

    # 2. Сбор данных и отладка
    comparison_data = {}

    print("\n" + "=" * 100)
    print(f"DEBUG CASH FLOW | ОГРАНИЧЕНИЕ ПО 1.02.50 | КОНСОЛИДИРОВАНО: {is_consolidated}")
    print("=" * 100)

    for year in selected_years:
        comparison_data[year] = {key: {'fact': [], 'forecast': []} for key in cash_categories}
        for key, cfg in cash_categories.items():
            facts = []
            print(f"\n[Группа: {key} | {year}]")

            for m in months:
                p = date(year, m, 1)
                base_qs = TrialBalance.objects.filter(period=p)
                if entity_id: base_qs = base_qs.filter(entity_id=entity_id)

                final_qs = get_filtered_qs(base_qs, cfg['code'], cfg['field'])

                details = final_qs.values('account_code', 'entity__name').annotate(amount=Sum(cfg['field']))
                month_sum = 0

                if details.exists():
                    print(f"  Месяц {m:02d}:")
                    for entry in details:
                        amt = float(entry['amount'] or 0)
                        if amt != 0:
                            print(f"    - {entry['account_code']:10} | {amt:15,.2f} | {entry['entity__name']}")
                            month_sum += amt
                    print(f"    СУММА: {month_sum:,.2f}")

                facts.append(month_sum)

            comparison_data[year][key]['fact'] = facts
            current_hist = [v for v in facts if v > 0]
            base_trend = np.mean(current_hist[-2:]) if len(current_hist) >= 2 else last_trends[key]
            forecast = [facts[i] if facts[i] > 0 else round(base_trend * seasonality_map[key][i], 2) for i in range(12)]
            comparison_data[year][key]['forecast'] = forecast

    return render(request, 'analytics/cash_flow_report.html', {
        'selected_years': selected_years,
        'available_years': available_years,
        'entities': entities,
        'selected_entity_id': int(entity_id) if (entity_id and entity_id.isdigit()) else None,
        'comparison_data_json': json.dumps(comparison_data),
        'months_labels': json.dumps(
            ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"])
    })