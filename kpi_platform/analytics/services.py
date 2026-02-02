import pandas as pd
from .models import Category, PnLData, Entity
from decimal import Decimal
import re


def clean_decimal(value):
    if pd.isna(value) or str(value).strip() == '' or str(value).strip() == '-':
        return Decimal('0.00')
    # Убираем пробелы и лишние символы, заменяем запятую на точку
    cleaned = re.sub(r'[^\d.,-]', '', str(value)).replace(',', '.')
    try:
        return Decimal(cleaned)
    except:
        return Decimal('0.00')


def process_pnl_file(file, entity_obj, period_date):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        # Указываем header=None, чтобы самим контролировать строки
        df = pd.read_excel(file, header=None)

    # Начинаем с 4-й строки (индекс 4 в Excel, 3 в Python)
    for index, row in df.iloc[3:].iterrows():
        # Пробуем взять название из колонки B, если там пусто - из колонки A
        val_a = str(row.iloc[0]).strip()
        val_b = str(row.iloc[1]).strip()

        # Если в B пусто (nan), берем значение из А.
        # Это часто бывает в итоговых строках Excel при экспорте
        if val_b == 'nan' or not val_b:
            name = val_a
        else:
            name = val_b

        # Пропускаем, если совсем ничего нет
        if not name or name == 'nan' or 'наименование' in name.lower():
            continue

        # ЛОГИКА ИТОГА: если в колонке А нет ни одной цифры
        # (в итоговых строках там либо пусто, либо текст "Итого")
        has_digit = any(char.isdigit() for char in val_a)
        is_total = not has_digit

        category, _ = Category.objects.update_or_create(
            name=name,
            defaults={
                'order': index,
                'is_total': is_total
            }
        )

        # Значения План/Факт обычно в 3 и 4 колонках (индексы 2 и 3)
        fact_val = clean_decimal(row.iloc[2])
        plan_val = clean_decimal(row.iloc[3])

        PnLData.objects.update_or_create(
            entity=entity_obj,
            category=category,
            period=period_date,
            defaults={'fact': fact_val, 'plan': plan_val}
        )


def process_osv_file(file, entity_obj, period_date):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    # В твоем файле ОСВ заголовки на 4-й строке (индекс 3)
    # Колонки: 0: Счет, 1: Наименование, 5: Дебет оборот, 6: Кредит оборот
    df_data = df.iloc[4:].reset_index(drop=True)

    from .models import TrialBalance

    for index, row in df_data.iterrows():
        account_code = str(row.iloc[0]).strip()
        account_name = str(row.iloc[1]).strip()

        # Пропускаем пустые строки и итоги
        if not account_code or account_code == 'nan' or 'ИТОГО' in account_code.upper():
            continue

        # Очищаем цифры
        debit_val = clean_decimal(row.iloc[5])
        credit_val = clean_decimal(row.iloc[6])

        # Сохраняем в БД
        TrialBalance.objects.update_or_create(
            entity=entity_obj,
            period=period_date,
            account_code=account_code,
            defaults={
                'account_name': account_name,
                'debit_turnover': debit_val,
                'credit_turnover': credit_val,
            }
        )