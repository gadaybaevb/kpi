from django.views.generic import ListView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from .models import KPI, Indicator, KPIBonus
from users.models import Department, User
from django.views import View
from core.utils import log_action
import os
import urllib.parse
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
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import get_template
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from weasyprint import HTML


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
        return self.request.user.role in ['hr', 'admin', 'dept_head']

    def post(self, request, pk):
        indicator = get_object_or_404(Indicator, pk=pk)
        kpi = indicator.kpi

        if indicator.status != 'approved':
            indicator.status = 'approved'
            indicator.save()
            messages.success(request, f"Показатель '{indicator.name}' подтвержден.")

            # Проверка: все ли индикаторы этого KPI одобрены?
            if kpi.indicators.exclude(status='approved').count() == 0:
                if hasattr(kpi, 'bonus_setup'):
                    bonus = kpi.bonus_setup
                    total_score = kpi.get_total_score()

                    # Логика трешхолдов из модели
                    if total_score < bonus.threshold_min:
                        bonus.final_payout = 0
                    elif total_score > bonus.threshold_max:
                        # Ограничиваем выплату максимумом (например, не более 120%)
                        bonus.final_payout = (bonus.threshold_max / 100) * float(bonus.target_amount)
                    else:
                        bonus.final_payout = (total_score / 100) * float(bonus.target_amount)

                    bonus.is_calculated = True
                    bonus.save()
                    messages.info(request, f"KPI '{kpi.name}' полностью утвержден. Сумма: {bonus.final_payout}")

        return redirect('hr_review_list')


class DashboardView(LoginRequiredMixin, ListView):
    template_name = 'kpi/dashboard.html'
    model = KPI

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # 1. Список доступных месяцев из БД
        db_months = KPI.objects.filter(is_active=True).dates('for_month', 'month', order='DESC')
        context['available_months'] = db_months if db_months else [timezone.now().date().replace(day=1)]

        # 2. Определение выбранного месяца
        month_str = self.request.GET.get('month')
        if month_str:
            try:
                selected_date = datetime.strptime(month_str, '%Y-%m').date()
            except:
                selected_date = context['available_months'][0]
        else:
            selected_date = context['available_months'][0]
        context['selected_month'] = selected_date

        # 3. Фильтрация департаментов по ролям
        if user.role in ['admin', 'hr']:
            target_departments = Department.objects.all()
        else:
            target_departments = Department.objects.filter(id=user.department.id) if user.department else []

        departments_data = []
        total_perf_sum = 0
        total_emp_count = 0
        grand_total_money = 0.0

        for dept in target_departments:
            dept_employees = User.objects.filter(department=dept)
            emp_list = []
            dept_sum_score = 0
            dept_total_money = 0.0

            # Все KPI отдела для сводки справа
            all_dept_kpis = KPI.objects.filter(
                department=dept, is_active=True,
                for_month__month=selected_date.month,
                for_month__year=selected_date.year
            ).select_related('employee')

            for emp in dept_employees:
                emp_kpis = KPI.objects.filter(
                    employee=emp, is_active=True,
                    for_month__month=selected_date.month,
                    for_month__year=selected_date.year
                ).select_related('bonus_setup')

                emp_avg_score = 0
                emp_money = 0.0
                emp_target_money = 0.0

                if emp_kpis.exists():
                    scores = [k.get_total_score() for k in emp_kpis]
                    emp_avg_score = sum(scores) / len(scores)

                    for k in emp_kpis:
                        bonus = getattr(k, 'bonus_setup', None)
                        if bonus:
                            emp_target_money += float(bonus.target_amount or 0)
                            score = float(k.get_total_score())

                            if bonus.is_calculated:
                                emp_money += float(bonus.final_payout or 0)
                            else:
                                t_min = float(bonus.threshold_min or 80)
                                if score >= t_min:
                                    t_max = float(bonus.threshold_max or 120)
                                    s_clamped = min(score, t_max)
                                    emp_money += (s_clamped / 100) * float(bonus.target_amount or 0)

                emp_list.append({
                    'id': emp.id,
                    'full_name': emp.get_full_name() or emp.username,
                    'position': emp.position.name if emp.position else "-",
                    'current_score': emp_avg_score,
                    'target_money': emp_target_money,
                    'money': emp_money
                })
                dept_sum_score += emp_avg_score
                dept_total_money += emp_money

            # Расчет средних по отделу
            dept_avg = dept_sum_score / dept_employees.count() if dept_employees.exists() else 0
            total_perf_sum += dept_sum_score
            total_emp_count += dept_employees.count()
            grand_total_money += dept_total_money

            departments_data.append({
                'info': dept,
                'employees': emp_list,
                'kpis': all_dept_kpis,
                'avg': dept_avg,
                'total_money': dept_total_money
            })

        context['departments_data'] = departments_data
        context['grand_total_money'] = grand_total_money
        context['dept_avg'] = total_perf_sum / total_emp_count if total_emp_count > 0 else 0

        # ИСПРАВЛЕННАЯ ПРОВЕРКА: Закрыт ли месяц?
        # Мы проверяем только АКТИВНЫЕ KPI. Если за этот месяц есть хоть один активный KPI,
        # который уже зафиксирован (is_calculated=True), то считаем период закрытым.
        context['is_month_closed'] = KPIBonus.objects.filter(
            kpi__for_month__month=selected_date.month,
            kpi__for_month__year=selected_date.year,
            kpi__is_active=True,
            is_calculated=True
        ).exists()

        # Данные для графика статусов
        status_filter = Q(kpi__for_month__month=selected_date.month, kpi__for_month__year=selected_date.year,
                          kpi__is_active=True)
        status_counts = Indicator.objects.filter(status_filter).values('status').annotate(total=Count('id'))
        status_map = {'draft': 0, 'on_review': 1, 'approved': 2, 'rejected': 3}
        chart_values = [0, 0, 0, 0]
        for item in status_counts:
            if item['status'] in status_map:
                chart_values[status_map[item['status']]] = item['total']
        context['chart_data'] = chart_values

        return context


class KPICreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = KPI
    form_class = KPICreateForm
    template_name = 'kpi/kpi_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.role in ['hr', 'admin']


@login_required
def export_kpi_pdf(request):
    month_str = request.GET.get('month')

    if not month_str:
        return HttpResponse("Месяц не указан", status=400)

    try:
        selected_date = datetime.strptime(month_str, '%Y-%m').date()
    except ValueError:
        return HttpResponse("Неверный формат даты", status=400)

    departments = Department.objects.all()
    data = []
    total_company_bonus = 0
    company_perf_accumulator = 0

    chart_labels = []
    chart_values = []
    summary_table_data = []

    for dept in departments:
        dept_data = {
            'name': dept.name,
            'employees': [],
            'total_dept_money': 0,
            'avg_dept_perf': 0
        }

        users = User.objects.filter(department=dept)
        dept_perf_list = []

        for user in users:
            kpis = KPI.objects.filter(
                employee=user,
                for_month__month=selected_date.month,
                for_month__year=selected_date.year,
                is_active=True
            ).select_related('bonus_setup')

            if kpis.exists():
                emp_kpi_list = []
                emp_total_money = 0
                for k in kpis:
                    bonus = getattr(k, 'bonus_setup', None)
                    money = 0
                    if bonus:
                        if bonus.is_calculated:
                            money = float(bonus.final_payout or 0)
                        else:
                            score = float(k.get_total_score())
                            t_min = float(bonus.threshold_min or 80)
                            if score >= t_min:
                                t_max = float(bonus.threshold_max or 120)
                                s_clamped = min(score, t_max)
                                money = (s_clamped / 100) * float(bonus.target_amount or 0)

                    emp_total_money += money
                    emp_kpi_list.append({'name': k.name, 'perf': k.get_total_score(), 'money': money})

                emp_avg_perf = sum([k['perf'] for k in emp_kpi_list]) / len(emp_kpi_list)
                dept_perf_list.append(emp_avg_perf)

                dept_data['employees'].append({
                    'full_name': user.get_full_name() or user.username,
                    'kpis': emp_kpi_list,
                    'subtotal_money': emp_total_money,
                    'avg_perf': emp_avg_perf
                })
                dept_data['total_dept_money'] += emp_total_money

        if dept_data['employees']:
            dept_data['avg_dept_perf'] = sum(dept_perf_list) / len(dept_perf_list)
            data.append(dept_data)

            total_company_bonus += dept_data['total_dept_money']
            company_perf_accumulator += dept_data['avg_dept_perf']

            chart_labels.append(dept_data['name'])
            chart_values.append(float(dept_data['total_dept_money']))

    company_avg_perf = company_perf_accumulator / len(data) if data else 0

    for i in range(len(chart_labels)):
        share = (chart_values[i] / total_company_bonus * 100) if total_company_bonus > 0 else 0
        summary_table_data.append({
            'name': chart_labels[i],
            'amount': chart_values[i],
            'share': share
        })


    chart_config = {
        'type': 'pie',
        'data': {
            'labels': chart_labels,
            'datasets': [{
                'data': chart_values,
                'backgroundColor': ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6610f2', '#fd7e14', '#20c997']
            }]
        }
    }
    chart_url = f"https://quickchart.io/chart?c={urllib.parse.quote(str(chart_config))}"

    months_ru = {1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель', 5: 'Май', 6: 'Июнь',
                 7: 'Июль', 8: 'Август', 9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'}

    context = {
        'data': data,
        'period': months_ru.get(selected_date.month),
        'year': selected_date.year,
        'total_company_bonus': total_company_bonus,  # Проверьте это имя в шаблоне!
        'company_avg_perf': company_avg_perf,  # Проверьте это имя в шаблоне!
        'summary_table': summary_table_data,
        'chart_url': chart_url,
        'today': datetime.now(),
    }

    html_string = render_to_string('kpi/pdf_report.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="KPI_Report_{month_str}.pdf"'
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


class KPIUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = KPI
    form_class = KPICreateForm  # Та же форма, что и для создания
    template_name = 'kpi/kpi_form.html'  # Тот же шаблон
    success_url = reverse_lazy('admin_manage')


    def test_func(self):
        return self.request.user.role in ['hr', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Редактирование: {self.object.name}"
        return context


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


class CloseMonthView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        # Проверяем права (только HR или Admin)
        if request.user.role not in ['admin', 'hr']:
            messages.error(request, "У вас нет прав для выполнения этой операции.")
            return redirect('dashboard')

        month_str = request.POST.get('month')
        if not month_str:
            return redirect('dashboard')

        # Определяем дату
        selected_date = datetime.strptime(month_str, '%Y-%m').date()

        # Находим все KPI за этот месяц, у которых еще не зафиксирован бонус
        kpis = KPI.objects.filter(
            for_month__month=selected_date.month,
            for_month__year=selected_date.year,
            is_active=True
        ).select_related('bonus_setup')

        updated_count = 0
        for kpi in kpis:
            bonus = getattr(kpi, 'bonus_setup', None)
            if bonus and not bonus.is_calculated:
                # Проводим финальный расчет
                score = float(kpi.get_total_score())
                t_min = float(bonus.threshold_min or 80)
                t_max = float(bonus.threshold_max or 120)
                t_target = float(bonus.target_amount or 0)

                if score >= t_min:
                    calc_percent = min(score, t_max)
                    bonus.final_payout = (calc_percent / 100) * t_target
                else:
                    bonus.final_payout = 0

                bonus.is_calculated = True
                bonus.save()
                updated_count += 1

        messages.success(request, f"Месяц закрыт! Зафиксировано выплат: {updated_count}")
        return redirect(f"{reverse('dashboard')}?month={month_str}")

