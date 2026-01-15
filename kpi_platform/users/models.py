from django.db import models
from django.contrib.auth.models import AbstractUser


class Department(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Position(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название должности")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='positions')

    def __str__(self):
        return f"{self.name} ({self.department.name if self.department else 'Без отдела'})"

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('hr', 'HR'),
        ('dept_head', 'Department Head'),
        ('employee', 'Employee'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    superior = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def unread_notifications_count(self):
        return self.notifications.filter(is_read=False).count()


