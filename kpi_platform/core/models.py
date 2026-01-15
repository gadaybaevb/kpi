from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255) # Например: "Created KPI", "Updated Fact"
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    changes = models.TextField(blank=True) # Здесь можно хранить JSON старых/новых значений