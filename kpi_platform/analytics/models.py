from django.db import models


class Entity(models.Model):
    name = models.CharField(max_length=255, verbose_name="Филиал/ГО")
    is_hq = models.BooleanField(default=False, verbose_name="Штаб-квартира")

    class Meta:
        verbose_name = "Орг. единица"
        verbose_name_plural = "Орг. единицы"

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name="Статья ОПУ")
    order = models.IntegerField(default=0, verbose_name="Порядок в отчете")
    is_total = models.BooleanField(default=False, verbose_name="Итоговая строка") # Новое поле

    class Meta:
        verbose_name = "Статья ОПУ"
        verbose_name_plural = "Справочник статей ОПУ"
        ordering = ['order']

    def __str__(self):
        return self.name


class PnLData(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name="Филиал")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name="Статья")
    period = models.DateField(verbose_name="Период (месяц)")
    plan = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="План")
    fact = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="Факт")

    class Meta:
        verbose_name = "Данные ОПУ"
        verbose_name_plural = "Данные ОПУ (План-Факт)"


class TrialBalance(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name="Филиал")
    period = models.DateField(verbose_name="Период")
    account_code = models.CharField(max_length=20, verbose_name="Номер счета")
    account_name = models.CharField(max_length=255, verbose_name="Название счета")
    debit_turnover = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Дебет оборот")
    credit_turnover = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Кредит оборот")
    subconto = models.JSONField(null=True, blank=True, verbose_name="Аналитика (Субконто)")

    class Meta:
        verbose_name = "Данные ОСВ"
        verbose_name_plural = "Данные ОСВ"