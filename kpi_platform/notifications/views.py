from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/list.html'
    context_object_name = 'notifications'

    def get_paginate_by(self, queryset):
        # Получаем количество из URL, по умолчанию 5
        return self.request.GET.get('per_page', 5)

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        current_filter = self.request.GET.get('filter', 'all')
        if current_filter == 'unread':
            qs = qs.filter(is_read=False)
        elif current_filter == 'read':
            qs = qs.filter(is_read=True)

        # Помечаем прочитанными
        qs_to_read = qs.filter(is_read=False)
        if qs_to_read.exists():
            qs_to_read.update(is_read=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_filter'] = self.request.GET.get('filter', 'all')
        context['per_page'] = self.get_paginate_by(self.get_queryset())
        return context