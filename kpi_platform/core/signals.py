from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from kpi.models import KPI, Indicator
from .models import AuditLog

@receiver(post_save, sender=KPI)
@receiver(post_save, sender=Indicator)
def log_save(sender, instance, created, **kwargs):
    action = "Created" if created else "Updated"
    # Пытаемся получить пользователя, если это возможно
    # Примечание: В сигналах нет прямого доступа к request.user без костылей, 
    # поэтому обычно здесь пишется системный лог или используется middleware.
    AuditLog.objects.create(
        action=action,
        model_name=sender.__name__,
        object_id=instance.id,
        changes=f"{instance}"
    )

@receiver(post_delete, sender=KPI)
@receiver(post_delete, sender=Indicator)
def log_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        action="Deleted",
        model_name=sender.__name__,
        object_id=instance.id,
        changes=f"Deleted object: {instance}"
    )