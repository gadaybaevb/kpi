from django.views.generic import ListView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from .models import KPI, Indicator
from users.models import Department, User
from django.shortcuts import redirect
from django.views import View
from core.utils import log_action
from django.db.models import Sum, Avg
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
User = get_user_model()
from django.views.generic.edit import CreateView
from .forms import KPICreateForm, IndicatorCreateForm, IndicatorUpdateFactForm, IndicatorRejectForm
import csv
from django.http import HttpResponse
from django.views.generic import DeleteView
from datetime import date, timedelta
from django.db import transaction
from django.contrib import messages
from django.views.generic import DetailView
from users.models import User  # Импортируем вашу модель пользователя
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime


class AdminRequiredMixin(UserPassesTestMixin):
    """Миксин, который ограничивает доступ только для администраторов."""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role == 'admin'


class MyKPIListView(LoginRequiredMixin, ListView):
    model = KPI
    template_name = 'kpi/my_kpi_list.html'
    context_object_name = 'kpis'

    def get_queryset(self):
        # Показываем только активные KPI текущего пользователя
        return KPI.objects.filter(
            employee=self.request.user,
            is_active=True
        ).prefetch_related('indicators').order_by('-for_month')


class IndicatorUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Indicator
    form_class = IndicatorCreateForm  # Используем полную форму
    template_name = 'kpi/indicator_add_form.html'

    def test_func(self):
        return self.request.user.role in ['admin', 'hr']

    def get_success_url(self):
        return reverse_lazy('kpi_indicators_detail', kwargs={'kpi_id': self.object.kpi.id})


class HRReviewListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Indicator
    template_name = 'kpi/hr_review_list.html'
    context_object_name = 'pending_indicators'

    def test_func(self):
        # Доступ только для HR, Admin и Глав департаментов
        return self.request.user.role in ['hr', 'admin', 'dept_head']

    def get_queryset(self):
        # Показываем только те, что ждут проверки
        return Indicator.objects.filter(status='on_review')


class ApproveIndicatorView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        # Проверяем, что одобряет не обычный сотрудник
        return self.request.user.role in ['hr', 'admin', 'dept_head']

    def post(self, request, pk):
        # 1. Безопасно получаем объект
        indicator = get_object_or_404(Indicator, pk=pk)

        # 2. Проверяем, не одобрен ли он уже (чтобы не дублировать логи)
        if indicator.status == 'approved':
            messages.info(request, f"Индикатор '{indicator.name}' уже был одобрен ранее.")
        else:
            indicator.status = 'approved'
            indicator.save()

            # 3. Добавляем системное уведомление для пользователя
            messages.success(request, f"Показатель '{indicator.name}' успешно подтвержден.")

            # Если есть логгер, записываем
            # log_action(request.user, f"Одобрил индикатор {indicator.id}", indicator)

        return redirect('hr_review_list')


class DashboardView(LoginRequiredMixin, ListView):
    template_name = 'kpi/dashboard.html'
    model = KPI

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # --- 0. Список месяцев (из всех KPI для админов, из своего отдела для остальных) ---
        if user.role in ['admin', 'hr']:
            db_months = KPI.objects.dates('for_month', 'month', order='DESC')
        else:
            db_months = KPI.objects.filter(department=user.department).dates('for_month', 'month', order='DESC')

        context['available_months'] = db_months if db_months else [timezone.now().date().replace(day=1)]

        # --- 1. Выбор периода ---
        month_str = self.request.GET.get('month')
        if month_str:
            try:
                selected_date = datetime.strptime(month_str, '%Y-%m').date()
            except (ValueError, TypeError):
                selected_date = context['available_months'][0]
        else:
            selected_date = context['available_months'][0]

        context['selected_month'] = selected_date

        # --- 2. Сбор данных по департаментам ---
        # Если HR/Admin - берем все отделы, иначе только свой
        if user.role in ['admin', 'hr']:
            target_departments = Department.objects.all()
        else:
            target_departments = Department.objects.filter(id=user.department.id) if user.department else []

        departments_data = []
        total_perf_sum = 0
        total_emp_count = 0

        for dept in target_departments:
            dept_employees = User.objects.filter(department=dept)
            emp_list = []
            dept_sum = 0

            for emp in dept_employees:
                emp_kpis = KPI.objects.filter(
                    employee=emp, is_active=True,
                    for_month__month=selected_date.month,
                    for_month__year=selected_date.year
                )

                avg_score = 0
                if emp_kpis.exists():
                    scores = [k.get_total_score() for k in emp_kpis]
                    avg_score = sum(scores) / len(scores)

                emp_list.append({
                    'full_name': emp.get_full_name() or emp.username,
                    'position': emp.position.name if emp.position else "-",
                    'current_score': avg_score,
                    'id': emp.id
                })
                dept_sum += avg_score

            dept_avg = dept_sum / dept_employees.count() if dept_employees.exists() else 0
            total_perf_sum += dept_sum
            total_emp_count += dept_employees.count()

            # Цели именно этого департамента
            d_kpis = KPI.objects.filter(
                department=dept, target_type='department', is_active=True,
                for_month__month=selected_date.month,
                for_month__year=selected_date.year
            )

            departments_data.append({
                'info': dept,
                'employees': emp_list,
                'avg': dept_avg,
                'kpis': d_kpis
            })

        context['departments_data'] = departments_data
        context['dept_avg'] = total_perf_sum / total_emp_count if total_emp_count > 0 else 0
        context['department_label'] = "Все департаменты" if user.role in ['admin', 'hr'] else user.department.name

        # --- 3. Статистика для Chart.js (общая по выбранным данным) ---
        status_filter = Q(kpi__for_month__month=selected_date.month, kpi__for_month__year=selected_date.year)
        if user.role not in ['admin', 'hr']:
            status_filter &= Q(kpi__department=user.department)

        status_counts = Indicator.objects.filter(status_filter).values('status').annotate(total=Count('id'))

        labels = ['Черновик', 'На проверке', 'Одобрено', 'Отклонено']
        values = [0, 0, 0, 0]
        status_map = {'draft': 0, 'on_review': 1, 'approved': 2, 'rejected': 3}

        for item in status_counts:
            if item['status'] in status_map:
                values[status_map[item['status']]] = item['total']

        context['chart_labels'] = labels
        context['chart_data'] = values

        return context


class KPICreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = KPI
    form_class = KPICreateForm
    template_name = 'kpi/kpi_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.role in ['hr', 'admin']


def export_kpi_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="kpi_report.csv"'

    writer = csv.writer(response)
    # Внутри export_kpi_csv
    writer.writerow(['KPI', 'Индикатор', 'Вес', 'Колич %', 'Качеств %', 'Итог %', 'Вклад в KPI'])

    indicators = Indicator.objects.all()
    for ind in indicators:
        writer.writerow([
            ind.kpi.name,
            ind.name,
            f"{ind.weight}%",
            ind.fact_quantitative,
            ind.fact_qualitative,
            f"{ind.total_performance}%",
            f"{ind.weighted_result}%"
        ])

    return response


class AdminKPIListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = KPI
    template_name = 'kpi/admin_manage.html'
    context_object_name = 'all_kpis'
    paginate_by = 15

    def test_func(self):
        return self.request.user.role == 'admin'

    def get_queryset(self):
        # Сортируем: сначала новые месяцы, потом активные, потом по версии
        return KPI.objects.all().order_by('-for_month', '-is_active', '-version', '-id')


# Метод для кнопки "Архивировать/Новая версия" прямо из списка
class ArchiveKPIRedirectView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.role == 'admin'

    def get(self, request, pk):
        kpi = KPI.objects.get(pk=pk)
        kpi.create_new_version()
        return redirect('admin_manage')


class KPIDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = KPI
    template_name = 'kpi/kpi_confirm_delete.html'
    success_url = reverse_lazy('admin_manage')

    def test_func(self):
        return self.request.user.role == 'admin'


class IndicatorAddView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Indicator
    form_class = IndicatorCreateForm
    template_name = 'kpi/indicator_add_form.html'

    def test_func(self):
        return self.request.user.role in ['admin', 'hr']

    def form_valid(self, form):
        # Привязываем индикатор к KPI, ID которого берем из URL
        form.instance.kpi_id = self.kwargs['kpi_id']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('admin_manage')


class KPIIndicatorListView(LoginRequiredMixin, ListView):
    model = Indicator
    template_name = 'kpi/kpi_indicators.html'
    context_object_name = 'indicators'

    def get_queryset(self):
        return Indicator.objects.filter(kpi_id=self.kwargs['kpi_id'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_kpi'] = KPI.objects.get(pk=self.kwargs['kpi_id'])
        return context


class IndicatorUpdateFactView(LoginRequiredMixin, UpdateView):
    model = Indicator
    form_class = IndicatorUpdateFactForm
    template_name = 'kpi/indicator_update_fact.html'

    def form_valid(self, form):
        # 1. Возвращаем на проверку
        form.instance.status = 'on_review'
        # 2. Очищаем старую причину отклонения, так как данные обновлены
        form.instance.rejection_reason = ""
        return super().form_valid(form)

    def get_success_url(self):
        # Если это сотрудник, возвращаем в его личный кабинет
        if self.request.user.role == 'employee':
            return reverse_lazy('my_kpi_list')
        return reverse_lazy('kpi_indicators_detail', kwargs={'kpi_id': self.object.kpi.id})


class IndicatorDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Indicator
    template_name = 'kpi/kpi_confirm_delete.html'  # Можно переиспользовать или создать новый

    def get_success_url(self):
        return reverse_lazy('kpi_indicators_detail', kwargs={'kpi_id': self.object.kpi.id})


def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    # Считаем количество заполненных (approved/on_review) и пустых (draft)
    stats = Indicator.objects.values('status').annotate(count=Count('id'))

    # Подготовка данных для JS
    context['chart_labels'] = ['Заполнено', 'На проверке', 'Ожидает (Черновик)']
    context['chart_data'] = [
        Indicator.objects.filter(status='approved').count(),
        Indicator.objects.filter(status='on_review').count(),
        Indicator.objects.filter(status='draft').count(),
    ]
    return context


class GenerateNextMonthKPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request):
        # Определяем первый день следующего месяца
        today = date.today()
        next_month_date = (today.replace(day=28) + timedelta(days=4)).replace(day=1)

        # Берем все активные шаблоны
        templates = KPI.objects.filter(is_template=True, is_active=True)

        if not templates.exists():
            messages.warning(request, "Нет активных шаблонов для генерации.")
            return redirect('admin_manage')

        created_count = 0
        with transaction.atomic():  # Чтобы если один упал, не создались остальные
            for temp in templates:
                # Проверяем, не созданы ли уже KPI для этого сотрудника на этот месяц
                exists = KPI.objects.filter(
                    employee=temp.employee,
                    for_month=next_month_date,
                    parent_template=temp  # Чтобы отличать от других версий
                ).exists()

                if not exists:
                    # Копируем KPI
                    new_kpi = KPI.objects.get(pk=temp.pk)
                    new_kpi.pk = None
                    new_kpi.is_template = False
                    new_kpi.for_month = next_month_date
                    new_kpi.parent_template = temp
                    new_kpi.save()

                    # Копируем индикаторы шаблона в новый KPI
                    for ind in temp.indicators.all():
                        ind.pk = None
                        ind.kpi = new_kpi
                        ind.fact_quantitative = 0
                        ind.fact_qualitative = 0
                        ind.status = 'draft'
                        ind.save()

                    created_count += 1

        messages.success(request, f"Успешно создано {created_count} KPI на {next_month_date.strftime('%B %Y')}")
        return redirect('admin_manage')


class RejectIndicatorView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Indicator
    form_class = IndicatorRejectForm
    template_name = 'kpi/indicator_reject_form.html'

    def test_func(self):
        return self.request.user.role in ['hr', 'admin', 'dept_head']

    def form_valid(self, form):
        form.instance.status = 'rejected'  # Меняем статус на "Отклонено"
        messages.error(self.request, f"Показатель {self.object.name} отклонен.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('hr_review_list')


class EmployeeDetailView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'kpi/employee_detail.html'
    context_object_name = 'target_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получаем все активные KPI этого сотрудника
        context['employee_kpis'] = KPI.objects.filter(
            employee=self.object,
            is_active=True,
            is_template=False
        ).order_by('-for_month')

        # Можно добавить расчет общего среднего балла сотрудника для профиля
        kpis = context['employee_kpis']
        if kpis:
            scores = [k.get_total_score() for k in kpis]
            context['total_avg'] = sum(scores) / len(scores)
        else:
            context['total_avg'] = 0

        return context