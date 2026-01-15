from django.urls import path
from .views import (
    DepartmentListView,
    DepartmentCreateView,
    DepartmentDeleteView,
    DepartmentUpdateView,
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserDeleteView,
    PositionListView,
    PositionUpdateView,
    PositionCreateView,
    PositionDeleteView,
)

urlpatterns = [
    # Пользователи
    path('staff/', UserListView.as_view(), name='user_list'),
    path('staff/add/', UserCreateView.as_view(), name='user_create'),
    path('staff/edit/<int:pk>/', UserUpdateView.as_view(), name='user_update'),
    path('staff/delete/<int:pk>/', UserDeleteView.as_view(), name='user_delete'),

    # Департаменты
    path('departments/', DepartmentListView.as_view(), name='department_list'),
    path('departments/add/', DepartmentCreateView.as_view(), name='department_create'),
    path('departments/edit/<int:pk>/', DepartmentUpdateView.as_view(), name='department_edit'),
    path('departments/delete/<int:pk>/', DepartmentDeleteView.as_view(), name='department_delete'),

    #Position
    path('positions/', PositionListView.as_view(), name='position_list'),
    path('positions/add/', PositionCreateView.as_view(), name='position_create'),
    path('positions/edit/<int:pk>/', PositionUpdateView.as_view(), name='position_edit'),
    path('positions/delete/<int:pk>/', PositionDeleteView.as_view(), name='position_delete'),
]