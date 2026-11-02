"""
Preparation app models: PreparationPlan, IngredientIndent
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class PreparationPlan(models.Model):
    """
    Preparation guidance for a meal service: how many portions to prepare per dish,
    derived from the forecast + safety margin.
    """
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        APPROVED = 'approved', 'Approved'
        SENT_TO_KITCHEN = 'sent', 'Sent to Kitchen'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
    
    forecast = models.OneToOneField(
        'forecasting.Forecast', on_delete=models.CASCADE, related_name='preparation_plan'
    )
    menu_schedule = models.ForeignKey(
        'menu.MenuSchedule', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='preparation_plans'
    )
    
    # Portions to prepare (forecast * safety_margin)
    planned_portions = models.PositiveIntegerField()
    safety_margin_used = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.10'))
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    approved_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_plans'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'preparation_plan'
        verbose_name = 'Preparation Plan'
        verbose_name_plural = 'Preparation Plans'
        ordering = ['-forecast__date']
    
    def __str__(self):
        return (f"Plan for {self.forecast.dining_hall.name} - "
                f"{self.forecast.meal_service.name} on {self.forecast.date} "
                f"({self.planned_portions} portions)")


class PreparationDish(models.Model):
    """Per-dish preparation quantity in a PreparationPlan."""
    
    plan = models.ForeignKey(PreparationPlan, on_delete=models.CASCADE, 
                              related_name='dish_items')
    dish = models.ForeignKey('menu.Dish', on_delete=models.CASCADE)
    recipe = models.ForeignKey('menu.Recipe', on_delete=models.SET_NULL, null=True)
    
    portions_to_prepare = models.PositiveIntegerField()
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'preparation_dish'
        verbose_name = 'Preparation Dish'
        unique_together = ['plan', 'dish']
    
    def __str__(self):
        return f"{self.dish.name}: {self.portions_to_prepare} portions"


class IngredientIndent(models.Model):
    """
    Ingredient procurement indent generated from a PreparationPlan.
    Can be exported in procurement format.
    """
    
    class Status(models.TextChoices):
        GENERATED = 'generated', 'Generated'
        SUBMITTED = 'submitted', 'Submitted to Store'
        FULFILLED = 'fulfilled', 'Fulfilled'
        PARTIAL = 'partial', 'Partially Fulfilled'
    
    preparation_plan = models.OneToOneField(
        PreparationPlan, on_delete=models.CASCADE, related_name='ingredient_indent'
    )
    reference_number = models.CharField(max_length=50, unique=True)
    
    date_required = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GENERATED)
    
    total_estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Export
    exported_at = models.DateTimeField(null=True, blank=True)
    export_format = models.CharField(max_length=50, blank=True, 
                                      help_text='csv, excel, json')
    
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, 
        related_name='created_indents'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ingredient_indent'
        verbose_name = 'Ingredient Indent'
        verbose_name_plural = 'Ingredient Indents'
        ordering = ['-date_required']
    
    def __str__(self):
        return f"Indent {self.reference_number} for {self.date_required}"
    
    def generate_reference(self):
        from django.utils import timezone
        self.reference_number = f"IND-{timezone.now():%Y%m%d}-{self.pk:04d}"
        self.save(update_fields=['reference_number'])


class IndentItem(models.Model):
    """Single ingredient line in an IngredientIndent."""
    
    indent = models.ForeignKey(IngredientIndent, on_delete=models.CASCADE, 
                                related_name='items')
    ingredient = models.ForeignKey('menu.Ingredient', on_delete=models.CASCADE)
    
    quantity_required = models.DecimalField(
        max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))]
    )
    unit = models.CharField(max_length=20)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Fulfillment tracking
    quantity_fulfilled = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    
    class Meta:
        db_table = 'indent_item'
        verbose_name = 'Indent Item'
        unique_together = ['indent', 'ingredient']
    
    def __str__(self):
        return f"{self.ingredient.name}: {self.quantity_required} {self.unit}"
    
    @property
    def is_fulfilled(self):
        return self.quantity_fulfilled >= self.quantity_required
