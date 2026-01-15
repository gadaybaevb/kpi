from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Department


# Регистрируем Департаменты
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


# Регистрируем Кастомного Пользователя
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Поля, которые будут видны в списке пользователей
    list_display = ('username', 'email', 'role', 'department', 'is_staff')

    # Добавляем наши поля в форму редактирования в админке
    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительная информация', {'fields': ('role', 'department', 'position', 'superior')}),
    )

    # Поля для создания нового пользователя через админку
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Дополнительная информация', {'fields': ('role', 'department', 'position', 'superior')}),
    )