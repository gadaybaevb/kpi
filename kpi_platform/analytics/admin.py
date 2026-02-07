from django.contrib import admin
from .models import Entity, Category, PnLData, TrialBalance


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_hq')
    list_filter = ('is_hq',)
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'is_total')
    # Делаем поле 'name' ссылкой, чтобы освободить 'order' для редактирования
    list_display_links = ('name',)
    list_editable = ('order', 'is_total')
    search_fields = ('name',)


@admin.register(PnLData)
class PnLDataAdmin(admin.ModelAdmin):
    list_display = ('period', 'entity', 'category', 'plan', 'fact')
    list_filter = ('entity', 'period', 'category')
    search_fields = ('category__name', 'entity__name')
    date_hierarchy = 'period' # Удобная навигация по датам сверху


@admin.register(TrialBalance)
class TrialBalanceAdmin(admin.ModelAdmin):
    list_display = ('period', 'entity', 'account_code', 'account_name', 'debit_turnover', 'credit_turnover')
    list_filter = ('entity', 'period', 'account_code')
    search_fields = ('account_name', 'account_code', 'entity__name')
    date_hierarchy = 'period'
    # Субконто в формате JSON лучше просто отображать, но если нужно редактировать,
    # Django автоматически подставит удобное поле для JSON