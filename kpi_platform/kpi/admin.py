from django.contrib import admin
from .models import KPI, Indicator


# Экшн для создания новой версии
@admin.action(description="Создать новую версию (архивировать текущую)")
def make_new_version(modeladmin, request, queryset):
    for kpi in queryset:
        if kpi.is_active:
            kpi.create_new_version()


class IndicatorInline(admin.TabularInline):
    model = Indicator
    extra = 1


@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee', 'period', 'version', 'is_active', 'created_at')
    list_filter = ('period', 'target_type', 'is_active')
    inlines = [IndicatorInline]
    actions = [make_new_version]


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    # Убираем fact_value и добавляем новые поля
    list_display = ('name', 'kpi', 'weight', 'fact_quantitative', 'fact_qualitative', 'status', 'created_at')
    list_filter = ('status', 'indicator_type', 'kpi')
    search_fields = ('name',)