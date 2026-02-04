from django.urls import path
from .views import (
    upload_financial_data,
    EntityListView,
    EntityCreateView,
    EntityUpdateView,
    PnLDataListView,
    TrialBalanceListView,
    consolidated_report,
    branch_dashboard,
    analytics_index,
    upload_audit_calendar,
    consolidated_osv,
    annual_analytics,
    cash_flow_analytics,
)

urlpatterns = [
    # Главная страница модуля аналитики
    path('', analytics_index, name='analytics_index'),
# Аналитические отчеты
    path('dashboard/', branch_dashboard, name='branch_dashboard'),
    path('consolidated/', consolidated_report, name='consolidated_report'),
    path('consolidated_osv/', consolidated_osv, name='consolidated_osv'),
    path('annual_analytics/', annual_analytics, name='annual_analytics'),
    path('cash_flow/', cash_flow_analytics, name='cash_flow'),
    path('upload/', upload_financial_data, name='upload_financial_data'),
    # Справочник филиалов
    path('entities/', EntityListView.as_view(), name='entity_list'),
    path('entities/add/', EntityCreateView.as_view(), name='entity_create'),
    path('entities/<int:pk>/edit/', EntityUpdateView.as_view(), name='entity_edit'),

    # Данные
    path('pnl-report/', PnLDataListView.as_view(), name='pnl_report'),

    path('osv-report/', TrialBalanceListView.as_view(), name='osv_report'),
    path('audit/', upload_audit_calendar, name='upload_audit'),



]