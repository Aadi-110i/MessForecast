"""
Actuals & Waste models: ServiceActual, WasteRecord
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class ServiceActual(models.Model):
    """
    Post-service recording: prepared, served, leftover per dish per service.
    Captured on mobile-friendly kitchen screen.
    """
    
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='actuals'
    )
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='actuals'
    )
    date = models.DateField(db_index=True)
    
    # Link to preparation plan if available
    preparation_plan = models.ForeignKey(
        'preparation.PreparationPlan', on_delete=models.SET_NULL, 
        null=True, blank=True, related_name='actuals'
    )
    
    # Attendance actuals
    actual_attendance = models.PositiveIntegerField(default=0)
    
    recorded_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, 
        related_name='recorded_actuals'
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'service_actual'
        verbose_name = 'Service Actual'
        verbose_name_plural = 'Service Actuals'
        unique_together = ['meal_service', 'dining_hall', 'date']
        ordering = ['-date', 'meal_service']
    
    def __str__(self):
        return f"Actual: {self.dining_hall.name} - {self.meal_service.name} on {self.date}"
    
    @property
    def total_prepared_portions(self):
        return sum(d.portions_prepared for d in self.dish_actuals.all())
    
    @property
    def total_served_portions(self):
        return sum(d.portions_served for d in self.dish_actuals.all())
    
    @property
    def total_waste_portions(self):
        return self.total_prepared_portions - self.total_served_portions


class DishActual(models.Model):
    """Per-dish actual quantities within a ServiceActual."""
    
    service_actual = models.ForeignKey(
        ServiceActual, on_delete=models.CASCADE, related_name='dish_actuals'
    )
    dish = models.ForeignKey('menu.Dish', on_delete=models.CASCADE)
    recipe = models.ForeignKey('menu.Recipe', on_delete=models.SET_NULL, null=True, blank=True)
    
    portions_prepared = models.PositiveIntegerField(default=0)
    portions_served = models.PositiveIntegerField(default=0)
    
    # Raw waste in kg (weighed)
    waste_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Physical waste weight in kg (weighed)'
    )
    
    class Meta:
        db_table = 'dish_actual'
        verbose_name = 'Dish Actual'
        unique_together = ['service_actual', 'dish']
    
    def __str__(self):
        return (f"{self.dish.name}: {self.portions_prepared} prepared, "
                f"{self.portions_served} served, "
                f"{self.portions_leftover} leftover")
    
    @property
    def portions_leftover(self):
        return max(0, self.portions_prepared - self.portions_served)
    
    @property
    def waste_percentage(self):
        if self.portions_prepared > 0:
            return (self.portions_leftover / self.portions_prepared) * 100
        return 0


class WasteRecord(models.Model):
    """
    Computed waste record: cost of waste per dish per service.
    Derived from ServiceActual + ingredient costs.
    """
    
    service_actual = models.ForeignKey(
        ServiceActual, on_delete=models.CASCADE, related_name='waste_records'
    )
    dish_actual = models.OneToOneField(
        DishActual, on_delete=models.CASCADE, related_name='waste_record',
        null=True, blank=True
    )
    dish = models.ForeignKey('menu.Dish', on_delete=models.CASCADE)
    
    date = models.DateField(db_index=True)
    meal_service = models.ForeignKey('core.MealService', on_delete=models.CASCADE)
    dining_hall = models.ForeignKey('core.DiningHall', on_delete=models.CASCADE)
    
    # Quantities
    portions_wasted = models.PositiveIntegerField(default=0)
    weight_wasted_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    
    # Costs
    ingredient_cost_per_portion = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_waste_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Over-preparation cost (cost of preparing more than served)
    over_preparation_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    computed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'waste_record'
        verbose_name = 'Waste Record'
        verbose_name_plural = 'Waste Records'
        indexes = [
            models.Index(fields=['date', 'dining_hall']),
            models.Index(fields=['date', 'dish']),
        ]
        ordering = ['-date', '-total_waste_cost']
    
    def __str__(self):
        return (f"Waste: {self.dish.name} on {self.date} - "
                f"{self.portions_wasted} portions = ₹{self.total_waste_cost}")
    
    @classmethod
    def compute_from_dish_actual(cls, dish_actual):
        """Compute and save waste record from a DishActual."""
        recipe = dish_actual.recipe or dish_actual.dish.recipes.filter(is_default=True).first()
        cost_per_portion = Decimal('0')
        if recipe:
            cost_per_portion = recipe.cost_per_portion or Decimal('0')
        
        portions_wasted = dish_actual.portions_leftover
        total_cost = Decimal(str(portions_wasted)) * cost_per_portion
        
        obj, _ = cls.objects.update_or_create(
            dish_actual=dish_actual,
            defaults={
                'service_actual': dish_actual.service_actual,
                'dish': dish_actual.dish,
                'date': dish_actual.service_actual.date,
                'meal_service': dish_actual.service_actual.meal_service,
                'dining_hall': dish_actual.service_actual.dining_hall,
                'portions_wasted': portions_wasted,
                'weight_wasted_kg': dish_actual.waste_weight_kg,
                'ingredient_cost_per_portion': cost_per_portion,
                'total_waste_cost': total_cost,
                'over_preparation_cost': total_cost,
            }
        )
        return obj
