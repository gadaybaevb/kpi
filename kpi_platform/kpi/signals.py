from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Indicator, KPI  # Точка важна
from notifications.models import Notification
from django.db import models


@receiver(post_save, sender=Indicator)
def handle_indicator_status_change(sender, instance, created, **kwargs):
    """Отправка уведомлений при изменении статуса индикатора"""
    if not created:
        # Если статус изменился на "on_review", уведомляем HR или руководителя
        if instance.status == 'on_review':
            recipient = instance.kpi.employee.superior if instance.kpi.employee else None
            if recipient:
                Notification.objects.create(
                    recipient=recipient,
                    sender=instance.kpi.employee,
                    message=f"Сотрудник {instance.kpi.employee} внес данные по KPI: {instance.name}. Требуется проверка."
                )

        # Если статус изменился на "approved" или "rejected", уведомляем сотрудника
        elif instance.status in ['approved', 'rejected']:
            if instance.kpi.employee:
                Notification.objects.create(
                    recipient=instance.kpi.employee,
                    message=f"Статус вашего индикатора {instance.name} изменен на: {instance.get_status_display()}. Комментарий: {instance.hr_comment}"
                )


@receiver(post_save, sender=Indicator)
def update_department_kpi(sender, instance, **kwargs):
    # Нас интересует только когда статус стал 'approved'
    if instance.status == 'approved' and instance.kpi.target_type == 'employee':
        dept = instance.kpi.employee.department
        if dept:
            # Ищем KPI департамента с таким же названием (или по логике связи)
            dept_kpi = KPI.objects.filter(
                department=dept,
                target_type='department',
                name=instance.kpi.name,
                is_active=True
            ).first()

            if dept_kpi:
                # Находим соответствующий индикатор в KPI департамента
                dept_indicator = dept_kpi.indicators.filter(name=instance.name).first()
                if dept_indicator:
                    # Считаем сумму всех одобренных фактов сотрудников этого департамента
                    total_fact = Indicator.objects.filter(
                        kpi__department=dept,
                        kpi__target_type='employee',
                        name=instance.name,
                        status='approved'
                    ).aggregate(models.Sum('fact_value'))['fact_value__sum'] or 0

                    dept_indicator.fact_value = total_fact
                    dept_indicator.save()