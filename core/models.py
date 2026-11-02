"""
Core models: User with roles, DiningHall, MealService
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user model with mess-specific roles."""
    
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        KITCHEN_STAFF = 'kitchen_staff', 'Kitchen Staff'
        MESS_MANAGER = 'mess_manager', 'Mess Manager'
        MESS_ADMIN = 'mess_admin', 'Mess Administrator'
        FINANCE_OFFICER = 'finance_officer', 'Finance Officer'
        ADMINISTRATOR = 'administrator', 'Administrator'
    
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    student_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    phone = models.CharField(max_length=15, blank=True)
    dining_hall = models.ForeignKey(
        'DiningHall', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_members', help_text='Assigned dining hall (for staff)'
    )
    rfid_uid = models.CharField(max_length=100, blank=True, null=True, unique=True, 
                                help_text='RFID card UID for attendance')
    mess_category = models.CharField(max_length=50, blank=True, 
                                     help_text='Mess fee category from ERP')
    is_active_student = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'core_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.username}) - {self.get_role_display()}"
    
    @property
    def is_kitchen_staff(self):
        return self.role == self.Role.KITCHEN_STAFF
    
    @property
    def is_mess_manager(self):
        return self.role == self.Role.MESS_MANAGER
    
    @property
    def is_mess_admin(self):
        return self.role == self.Role.MESS_ADMIN
    
    @property
    def is_finance_officer(self):
        return self.role == self.Role.FINANCE_OFFICER
    
    @property
    def is_administrator(self):
        return self.role == self.Role.ADMINISTRATOR


class DiningHall(models.Model):
    """Physical dining hall / mess unit."""
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    capacity = models.PositiveIntegerField(default=500)
    location = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    registered_strength = models.PositiveIntegerField(
        default=0, help_text='Official student count assigned to this hall'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_dining_hall'
        verbose_name = 'Dining Hall'
        verbose_name_plural = 'Dining Halls'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class MealService(models.Model):
    """A meal service slot (e.g., Breakfast, Lunch, Dinner, Snacks)."""
    
    class MealType(models.TextChoices):
        BREAKFAST = 'breakfast', 'Breakfast'
        LUNCH = 'lunch', 'Lunch'
        DINNER = 'dinner', 'Dinner'
        SNACKS = 'snacks', 'Snacks'
        BRUNCH = 'brunch', 'Brunch'
    
    name = models.CharField(max_length=100)
    meal_type = models.CharField(max_length=20, choices=MealType.choices)
    dining_hall = models.ForeignKey(DiningHall, on_delete=models.CASCADE, related_name='meal_services')
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    
    # Service-level configuration
    safety_margin = models.DecimalField(
        max_digits=4, decimal_places=2, default=1.10,
        help_text='Preparation multiplier (1.10 = 10% over forecast)'
    )
    max_over_preparation_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00,
        help_text='Maximum allowed over-preparation percentage'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_meal_service'
        verbose_name = 'Meal Service'
        verbose_name_plural = 'Meal Services'
        unique_together = ['dining_hall', 'meal_type', 'start_time']
        ordering = ['dining_hall', 'start_time']
    
    def __str__(self):
        return f"{self.dining_hall.name} - {self.name} ({self.start_time:%H:%M})"


class CostRate(models.Model):
    """Ingredient cost rates for waste costing."""
    
    unit = models.CharField(max_length=50, help_text='Unit of measurement (kg, L, piece, etc.)')
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_cost_rate'
        verbose_name = 'Cost Rate'
        verbose_name_plural = 'Cost Rates'
    
    def __str__(self):
        return f"{self.unit}: ₹{self.cost_per_unit}"


class SystemConfiguration(models.Model):
    """Global system settings."""
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_system_config'
        verbose_name = 'System Configuration'
        verbose_name_plural = 'System Configurations'
    
    def __str__(self):
        return f"{self.key} = {self.value}"
    
    @classmethod
    def get_value(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default
