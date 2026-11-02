"""
Menu app models: Ingredient, Dish, Recipe, RecipeItem, Menu, MenuSchedule
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class Ingredient(models.Model):
    """Raw ingredient with costing information."""
    
    class Unit(models.TextChoices):
        KG = 'kg', 'Kilograms'
        G = 'g', 'Grams'
        L = 'L', 'Litres'
        ML = 'ml', 'Millilitres'
        PIECE = 'piece', 'Piece'
        DOZEN = 'dozen', 'Dozen'
        PACKET = 'packet', 'Packet'
        BAG = 'bag', 'Bag'
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    category = models.CharField(max_length=100, blank=True, 
                                help_text='e.g., Vegetables, Grains, Dairy, Protein')
    supplier = models.CharField(max_length=200, blank=True)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    
    # Procurement fields
    procurement_code = models.CharField(max_length=100, blank=True,
                                         help_text='Code used in procurement system')
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_ingredient'
        verbose_name = 'Ingredient'
        verbose_name_plural = 'Ingredients'
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.unit}) - ₹{self.cost_per_unit}/{self.unit}"


class Dish(models.Model):
    """A dish that can appear on menus."""
    
    class Category(models.TextChoices):
        MAIN = 'main', 'Main Course'
        SIDE = 'side', 'Side Dish'
        STARTER = 'starter', 'Starter'
        DESSERT = 'dessert', 'Dessert'
        BEVERAGE = 'beverage', 'Beverage'
        BREAD = 'bread', 'Bread'
        RICE = 'rice', 'Rice'
        DAL = 'dal', 'Dal/Lentils'
        SALAD = 'salad', 'Salad'
        SNACK = 'snack', 'Snack'
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(blank=True)
    is_vegetarian = models.BooleanField(default=True)
    is_vegan = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Allergen info
    allergens = models.CharField(max_length=500, blank=True,
                                  help_text='Comma-separated allergen list')
    
    # Image
    image = models.ImageField(upload_to='dishes/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_dish'
        verbose_name = 'Dish'
        verbose_name_plural = 'Dishes'
        ordering = ['category', 'name']
    
    def __str__(self):
        veg_label = "🟢" if self.is_vegetarian else "🔴"
        return f"{veg_label} {self.name} ({self.get_category_display()})"


class Recipe(models.Model):
    """Recipe for a dish: portion size + ingredient mapping."""
    
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, related_name='recipes')
    name = models.CharField(max_length=200, help_text='Recipe variant name')
    portions = models.PositiveIntegerField(default=100, 
                                            help_text='Number of portions this recipe makes')
    portion_size_grams = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text='Size of one portion in grams'
    )
    preparation_time_minutes = models.PositiveIntegerField(default=30)
    is_default = models.BooleanField(default=False, 
                                      help_text='Default recipe for this dish')
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_recipe'
        verbose_name = 'Recipe'
        verbose_name_plural = 'Recipes'
    
    def __str__(self):
        return f"{self.dish.name} - {self.name} ({self.portions} portions)"
    
    @property
    def cost_per_portion(self):
        """Calculate cost per portion from ingredients."""
        total = sum(
            item.quantity_per_batch * item.ingredient.cost_per_unit / self.portions
            for item in self.items.select_related('ingredient')
        )
        return round(total, 2)


class RecipeItem(models.Model):
    """A single ingredient in a recipe."""
    
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, 
                                   related_name='recipe_items')
    quantity_per_batch = models.DecimalField(
        max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of ingredient for the full batch (recipe.portions servings)'
    )
    is_optional = models.BooleanField(default=False)
    notes = models.CharField(max_length=300, blank=True)
    
    class Meta:
        db_table = 'menu_recipe_item'
        verbose_name = 'Recipe Item'
        verbose_name_plural = 'Recipe Items'
        unique_together = ['recipe', 'ingredient']
    
    def __str__(self):
        return f"{self.recipe.dish.name}: {self.quantity_per_batch} {self.ingredient.unit} {self.ingredient.name}"
    
    @property
    def quantity_per_portion(self):
        return self.quantity_per_batch / self.recipe.portions
    
    @property
    def cost_per_batch(self):
        return self.quantity_per_batch * self.ingredient.cost_per_unit


class Menu(models.Model):
    """A named menu grouping dishes for a specific meal service."""
    
    name = models.CharField(max_length=200)
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='menus'
    )
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='menus'
    )
    dishes = models.ManyToManyField(Dish, through='MenuDish')
    is_published = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, 
        related_name='created_menus'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_menu'
        verbose_name = 'Menu'
        verbose_name_plural = 'Menus'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.dining_hall.name} ({self.meal_service.name})"


class MenuDish(models.Model):
    """Through table for Menu <-> Dish with portion/serving specifics."""
    
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE)
    recipe = models.ForeignKey(Recipe, on_delete=models.SET_NULL, null=True, blank=True,
                                help_text='Specific recipe to use; null = dish default')
    is_main = models.BooleanField(default=False, help_text='Is this a main dish?')
    serving_order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        db_table = 'menu_menu_dish'
        unique_together = ['menu', 'dish']
        ordering = ['serving_order']
    
    def __str__(self):
        return f"{self.menu.name}: {self.dish.name}"


class MenuSchedule(models.Model):
    """Schedule a menu for a specific date."""
    
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name='schedules')
    date = models.DateField()
    is_active = models.BooleanField(default=True)
    
    # Override estimated attendance (optional)
    expected_attendance = models.PositiveIntegerField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, 
        related_name='menu_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'menu_schedule'
        verbose_name = 'Menu Schedule'
        verbose_name_plural = 'Menu Schedules'
        unique_together = ['menu', 'date']
        ordering = ['date']
    
    def __str__(self):
        return f"{self.menu.name} on {self.date}"
