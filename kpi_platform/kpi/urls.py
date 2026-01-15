from django.urls import path
from django.views.generic import TemplateView
from .views import (
    MyKPIListView, IndicatorUpdateView, HRReviewListView, ApproveIndicatorView, DashboardView, export_kpi_csv,
    AdminKPIListView, ArchiveKPIRedirectView, KPICreateView, IndicatorAddView, KPIDeleteView, KPIIndicatorListView,
    IndicatorUpdateFactView, IndicatorDeleteView, GenerateNextMonthKPIView, RejectIndicatorView, EmployeeDetailView
)

urlpatterns = [
    # Главная
    path('', TemplateView.as_view(template_name='index.html'), name='home'),

    # Управление KPI (Админ-панель)
    path('manage/', AdminKPIListView.as_view(), name='admin_manage'),
    path('manage/create/', KPICreateView.as_view(), name='kpi_create'),
    path('manage/delete/<int:pk>/', KPIDeleteView.as_view(), name='kpi_delete'),
    path('manage/archive/<int:pk>/', ArchiveKPIRedirectView.as_view(), name='kpi_archive'),

    # Детализация KPI и работа с индикаторами
    path('manage/kpi/<int:kpi_id>/indicators/', KPIIndicatorListView.as_view(), name='kpi_indicators_detail'),
    path('manage/kpi/<int:kpi_id>/add-indicator/', IndicatorAddView.as_view(), name='indicator_add'),

    # CRUD конкретного индикатора (кнопки в таблице)
    path('indicator/<int:pk>/edit/', IndicatorUpdateView.as_view(), name='indicator_edit'),  # Исправлено имя
    path('indicator/<int:pk>/delete/', IndicatorDeleteView.as_view(), name='indicator_delete'),  # Новое
    path('indicator/<int:pk>/update-fact/', IndicatorUpdateFactView.as_view(), name='indicator_update_fact'),
    path('manage/generate-next-month/', GenerateNextMonthKPIView.as_view(), name='generate_next_month'),

    # Пути для сотрудников (Личный кабинет)
    path('my-kpis/', MyKPIListView.as_view(), name='my_kpi_list'),

    # Проверка и Аналитика
    path('review/', HRReviewListView.as_view(), name='hr_review_list'),
    path('review/action/<int:pk>/', ApproveIndicatorView.as_view(), name='approve_indicator'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('export/', export_kpi_csv, name='export_kpi'),
    path('indicator/<int:pk>/reject/', RejectIndicatorView.as_view(), name='reject_indicator'),
    path('employee/<int:pk>/', EmployeeDetailView.as_view(), name='employee_detail'),
]