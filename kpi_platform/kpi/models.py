from django.db import models
from django.conf import settings
from users.models import Position, User


class KPI(models.Model):
    PERIOD_CHOICES = (
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    )
    TARGET_CHOICES = (
        ('company', 'Company'),
        ('department', 'Department'),
        ('position', 'Position'),
        ('employee', 'Employee'),
    )

    name = models.CharField(max_length=255)
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)

    department = models.ForeignKey('users.Department', on_delete=models.CASCADE, null=True, blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    is_template = models.BooleanField(default=False, verbose_name="Это шаблон?")
    parent_template = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    # Добавим дату, к которой относится экземпляр (например, 01.02.2026)
    for_month = models.DateField(null=True, blank=True, verbose_name="Период (месяц)")


    def create_new_version(self):
        """Метод для архивации текущего KPI и создания нового"""
        # 1. Запоминаем ID текущего (старого) KPI
        old_pk = self.pk

        # 2. Архивируем старый
        self.is_active = False
        self.save()

        # 3. Создаем новый объект на основе текущего
        self.pk = None
        self.version += 1
        self.is_active = True
        self.save()  # Теперь self — это новый объект с новым ID

        # 4. Копируем индикаторы
        old_indicators = Indicator.objects.filter(kpi_id=old_pk)
        # Внутри цикла копирования индикаторов:
        for ind in old_indicators:
            ind.pk = None
            ind.kpi = self
            ind.status = 'draft'
            ind.fact_quantitative = 0  # Обнуляем
            ind.fact_qualitative = 0  # Обнуляем
            ind.save()

        return self

    def __str__(self):
        return f"{self.name} (v{self.version})"

    class Meta:
        ordering = ['-created_at']

    def get_total_score(self):
        return sum(ind.weighted_result for ind in self.indicators.all())  # Вместо self.indicator_set.all()

    def save(self, *args, **kwargs):
        if self.for_month:
            # Автоматически ставим 1-е число месяца
            self.for_month = self.for_month.replace(day=1)
        super().save(*args, **kwargs)

    def get_period_label(self):
        if not self.for_month:
            return f"Версия {self.version}"

        if self.period == 'monthly':
            # Возвращает: "Январь 2026"
            return self.for_month.strftime('%B %Y')
        elif self.period == 'quarterly':
            # Рассчитываем номер квартала
            quarter = (self.for_month.month - 1) // 3 + 1
            return f"{quarter}-й Квартал {self.for_month.year}"
        elif self.period == 'yearly':
            return f"{self.for_month.year} год"
        return f"{self.for_month}"


class Indicator(models.Model):
    TYPE_CHOICES = (
        ('numeric', 'Numeric'),
        ('percent', 'Percentage'),
        ('binary', 'Binary'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('on_review', 'On Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    kpi = models.ForeignKey(KPI, related_name='indicators', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    indicator_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    plan_value = models.FloatField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    hr_comment = models.TextField(blank=True, null=True)
    weight = models.PositiveIntegerField(default=0, verbose_name="Вес (%)")
    desc_quantitative = models.TextField(blank=True, verbose_name="Количественный показатель")
    desc_qualitative = models.TextField(blank=True, verbose_name="Качественный показатель")

    # Трэшхолды (пороги)
    threshold_min = models.FloatField(default=80.0, verbose_name="Порог 80%")
    threshold_max = models.FloatField(default=125.0, verbose_name="Порог 125%")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    fact_quantitative = models.FloatField(default=0, verbose_name="Факт Колич. (%)")
    fact_qualitative = models.FloatField(default=0, verbose_name="Факт Качеств. (%)")
    rejection_reason = models.TextField(null=True, blank=True, verbose_name="Причина отклонения")

    @property
    def total_performance(self):
        """
        Считает % выполнения индикатора.
        (Колич % + Качеств %) / 2
        Например: (100% + 90%) / 2 = 95% выполнения индикатора.
        """
        return (self.fact_quantitative + self.fact_qualitative) / 2

    @property
    def weighted_result(self):
        """
        Считает вклад в общий KPI.
        Если вес 20%, а выполнение 95%, то результат 19%.
        """
        return (self.total_performance * self.weight) / 100

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


class KPIBonus(models.Model):
    kpi = models.OneToOneField(KPI, on_delete=models.CASCADE, related_name='bonus_setup')
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Целевая сумма")
    threshold_min = models.FloatField(default=80.0, verbose_name="Минимальный порог (%)")
    threshold_max = models.FloatField(default=125.0, verbose_name="Максимальный порог (%)")
    final_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Итого к выплате")
    is_calculated = models.BooleanField(default=False)

    def __str__(self):
        return f"Bonus for {self.kpi.name}"


# models.py
class MonthStatus(models.Model):
    month = models.DateField(unique=True, verbose_name="Месяц")
    is_closed = models.BooleanField(default=False, verbose_name="Статус закрытия")
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    closed_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.month.strftime('%B %Y')} - {'Закрыт' if self.is_closed else 'Открыт'}"