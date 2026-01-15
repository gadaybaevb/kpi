from django.views.generic import ListView, UpdateView, CreateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from .forms import CustomUserCreationForm, UserUpdateForm
from .models import User, Department, Position
from django.db.models import Count


# Общий миксин для проверки прав админа
class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == 'admin'


# --- CRUD для Пользователей ---
# Создание сотрудника
class UserCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user_list')


class UserListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 10  # Количество пользователей на одной странице

    def get_queryset(self):
        # Рекомендуется добавить сортировку, чтобы пагинация работала корректно
        return User.objects.all().order_by('last_name', 'first_name')


class UserUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user_list')


# Удаление
class UserDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = User
    template_name = 'users/user_confirm_delete.html'
    success_url = reverse_lazy('user_list')


# --- CRUD для Департаментов ---
class DepartmentListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Department
    template_name = 'users/department_list.html'
    context_object_name = 'departments'
    paginate_by = 10  # Количество департаментов на страницу

    def get_queryset(self):
        # Добавляем подсчет сотрудников (user_set) сразу в запрос
        return Department.objects.annotate(user_count=Count('user')).order_by('name')


class DepartmentCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Department
    fields = ['name']
    template_name = 'users/department_form.html'
    success_url = reverse_lazy('department_list')


class DepartmentUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Department
    fields = ['name']
    template_name = 'users/department_form.html'
    success_url = reverse_lazy('department_list')


class DepartmentDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Department
    template_name = 'users/confirm_delete.html'
    success_url = reverse_lazy('department_list')


class PositionListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Position
    template_name = 'users/position_list.html'
    context_object_name = 'positions'
    paginate_by = 15  # Количество должностей на страницу

    def get_queryset(self):
        # Оптимизированный запрос с подсчетом сотрудников и загрузкой связанных департаментов
        return Position.objects.select_related('department').annotate(
            emp_count=Count('user')
        ).order_by('department__name', 'name')


class PositionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Position
    fields = ['name', 'department']
    template_name = 'users/position_form.html'
    success_url = reverse_lazy('position_list')


class PositionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Position
    fields = ['name', 'department']
    template_name = 'users/position_form.html'
    success_url = reverse_lazy('position_list')


class PositionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Position
    template_name = 'users/confirm_delete.html'
    success_url = reverse_lazy('position_list')