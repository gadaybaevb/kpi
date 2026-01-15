from django.core.management.base import BaseCommand
from kpi.models import KPI, Indicator
from datetime import date


class Command(BaseCommand):
    def handle(self, *args, **options):
        templates = KPI.objects.filter(is_template=True, is_active=True)
        for temp in templates:
            # Создаем копию для текущего месяца
            new_kpi = temp
            new_kpi.pk = None
            new_kpi.is_template = False
            new_kpi.target_date = date.today().replace(day=1)
            new_kpi.save()

            # Копируем индикаторы
            for ind in temp.indicators.all():
                ind.pk = None
                ind.kpi = new_kpi
                ind.status = 'draft'
                ind.save()