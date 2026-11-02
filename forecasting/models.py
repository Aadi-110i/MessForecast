"""
Forecasting app models: Forecast with confidence intervals
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class ForecastModel(models.Model):
    """Configuration for the forecasting method being used."""
    
    class MethodType(models.TextChoices):
        MOVING_AVERAGE = 'moving_avg', 'Moving Average (Baseline)'
        WEIGHTED_MA = 'weighted_ma', 'Weighted Moving Average'
        EXPONENTIAL_SMOOTHING = 'exp_smoothing', 'Exponential Smoothing'
        LINEAR_REGRESSION = 'linear_reg', 'Linear Regression'
        PROPHET = 'prophet', 'Prophet (Facebook)'
        GRADIENT_BOOST = 'gradient_boost', 'Gradient Boosting'
    
    name = models.CharField(max_length=200)
    method = models.CharField(max_length=30, choices=MethodType.choices, 
                               default=MethodType.WEIGHTED_MA)
    is_active = models.BooleanField(default=True)
    
    # Parameters (stored as JSON-compatible dict in text for flexibility)
    lookback_days = models.PositiveIntegerField(default=28, 
                                                 help_text='Days of history to use')
    weekday_weight = models.DecimalField(max_digits=4, decimal_places=2, default=0.3,
                                          help_text='Weight for same-weekday pattern')
    recency_weight = models.DecimalField(max_digits=4, decimal_places=2, default=0.5,
                                          help_text='Weight for recent values')
    event_weight = models.DecimalField(max_digits=4, decimal_places=2, default=0.2,
                                        help_text='Weight for calendar event adjustments')
    
    description = models.TextField(blank=True, 
                                    help_text='Plain-language explanation for mess managers')
    
    # Performance tracking
    current_mape = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                        help_text='Current Mean Absolute Percentage Error')
    mape_threshold_upgrade = models.DecimalField(
        max_digits=6, decimal_places=2, default=15.00,
        help_text='MAPE threshold (%) above which to consider model upgrade'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'forecast_model_config'
        verbose_name = 'Forecast Model'
        verbose_name_plural = 'Forecast Models'
    
    def __str__(self):
        return f"{self.name} ({self.get_method_display()})"


class Forecast(models.Model):
    """
    A generated attendance forecast for a specific meal service on a date.
    """
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        SUPERSEDED = 'superseded', 'Superseded by newer forecast'
    
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='forecasts'
    )
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='forecasts'
    )
    date = models.DateField(db_index=True)
    
    forecast_model = models.ForeignKey(
        ForecastModel, on_delete=models.SET_NULL, null=True, related_name='forecasts'
    )
    
    # Point estimate
    predicted_attendance = models.PositiveIntegerField()
    
    # Confidence interval
    lower_bound = models.PositiveIntegerField(help_text='80% CI lower bound')
    upper_bound = models.PositiveIntegerField(help_text='80% CI upper bound')
    
    # Contextual features used
    weekday = models.PositiveSmallIntegerField(help_text='0=Monday, 6=Sunday')
    is_holiday = models.BooleanField(default=False)
    is_exam_period = models.BooleanField(default=False)
    event_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.00'))
    
    # History used
    historical_avg = models.DecimalField(max_digits=8, decimal_places=2, 
                                          null=True, blank=True)
    same_weekday_avg = models.DecimalField(max_digits=8, decimal_places=2, 
                                            null=True, blank=True)
    data_points_used = models.PositiveSmallIntegerField(default=0,
                                                         help_text='Number of historical records used')
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    # Actuals (filled after service)
    actual_attendance = models.PositiveIntegerField(null=True, blank=True)
    forecast_error = models.DecimalField(max_digits=8, decimal_places=2, 
                                          null=True, blank=True,
                                          help_text='actual - predicted')
    mape = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                help_text='Mean Absolute Percentage Error for this forecast')
    
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.CharField(max_length=100, default='system',
                                     help_text='User or task that generated this forecast')
    
    class Meta:
        db_table = 'forecast'
        verbose_name = 'Forecast'
        verbose_name_plural = 'Forecasts'
        indexes = [
            models.Index(fields=['date', 'meal_service', 'dining_hall']),
            models.Index(fields=['date', 'status']),
        ]
        ordering = ['-date', 'meal_service']
    
    def __str__(self):
        return (f"Forecast {self.date} | {self.dining_hall.name} - {self.meal_service.name} "
                f"| {self.predicted_attendance} (±{self.confidence_range})")
    
    @property
    def confidence_range(self):
        return self.upper_bound - self.lower_bound
    
    def compute_accuracy(self):
        """Compute MAPE after actuals are available."""
        if self.actual_attendance and self.predicted_attendance:
            self.forecast_error = self.actual_attendance - self.predicted_attendance
            if self.actual_attendance > 0:
                self.mape = abs(self.forecast_error / self.actual_attendance) * 100
            self.save(update_fields=['forecast_error', 'mape'])
        return self.mape


class ForecastAccuracyReport(models.Model):
    """Weekly/monthly MAPE tracking per meal service for manager review."""
    
    class Period(models.TextChoices):
        WEEKLY = 'weekly', 'Weekly'
        MONTHLY = 'monthly', 'Monthly'
    
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='accuracy_reports'
    )
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='accuracy_reports'
    )
    period_type = models.CharField(max_length=10, choices=Period.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    
    forecasts_count = models.PositiveIntegerField()
    mean_mape = models.DecimalField(max_digits=6, decimal_places=2)
    median_mape = models.DecimalField(max_digits=6, decimal_places=2)
    max_mape = models.DecimalField(max_digits=6, decimal_places=2)
    min_mape = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Trend
    previous_mape = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    mape_trend = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                      help_text='Change in MAPE from previous period')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'forecast_accuracy_report'
        verbose_name = 'Forecast Accuracy Report'
        unique_together = ['meal_service', 'dining_hall', 'period_type', 'period_start']
        ordering = ['-period_start']
    
    def __str__(self):
        return f"{self.get_period_type_display()} accuracy: {self.mean_mape:.1f}% MAPE ({self.period_start})"
