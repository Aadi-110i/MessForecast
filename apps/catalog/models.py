"""M1 - Master data: dining halls, ingredients, dishes, recipes and cost rates.

This is the foundation every other module reads from. A dish's cost is not
stored on the dish: it is derived from its active recipe and the current cost
rate of every ingredient, so a price change in one ingredient flows through to
waste costing without anyone editing a menu.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class DiningHall(TimeStampedModel):
    """A physical mess location with its own service window."""

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=16, unique=True)
    location = models.CharField(
        max_length=160, blank=True, default="",
        help_text="Where the hall is on campus, for the kitchen staff who work there",
    )
    capacity = models.PositiveIntegerField(default=0, help_text="Seated / serving capacity")
    registered_strength = models.PositiveIntegerField(
        default=0,
        help_text="Students registered with this mess. The default for new meal services.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Ingredient(TimeStampedModel):
    """A raw material the kitchen buys and cooks."""

    class BaseUnit(models.TextChoices):
        KG = "kg", "Kilogram"
        G = "g", "Gram"
        L = "l", "Litre"
        ML = "ml", "Millilitre"
        PIECE = "piece", "Piece"
        BUNDLE = "bundle", "Bundle"
        DOZEN = "dozen", "Dozen"

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=24, unique=True)
    base_unit = models.CharField(max_length=12, choices=BaseUnit.choices, default=BaseUnit.KG)
    purchase_pack_size = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("1"),
        help_text="How much one purchased pack contains, expressed in base units",
    )
    purchase_pack_unit = models.CharField(max_length=64, blank=True, default="")
    category = models.CharField(max_length=64, blank=True, default="")
    stock_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        help_text=(
            "Quantity on hand in base units, when the mess counts its stock. "
            "Null means the mess does not track stock for this ingredient, which "
            "is the honest answer rather than a zero that was never counted."
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Ingredients"

    def __str__(self) -> str:
        return self.name

    def current_cost_rate(self, on_date: dt.date | None = None) -> "CostRate | None":
        """Latest cost rate effective on ``on_date`` (campus-wide rate preferred)."""
        on_date = on_date or dt.date.today()
        queryset = CostRate.objects.filter(
            ingredient=self, effective_from__lte=on_date
        ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
        rates = list(queryset.order_by("-effective_from"))
        for rate in rates:
            if rate.hall_id is None:
                return rate
        return rates[0] if rates else None

    def unit_cost(self, on_date: dt.date | None = None) -> Decimal:
        """Cost of one base unit, falling back to zero when no rate is on file."""
        rate = self.current_cost_rate(on_date)
        return rate.unit_cost if rate else Decimal("0")


class Dish(TimeStampedModel):
    """A cooked item on a menu."""

    class Category(models.TextChoices):
        STAPLE = "STAPLE", "Staple / rice / bread"
        VEG = "VEG", "Vegetable curry"
        NONVEG = "NONVEG", "Non-vegetable curry"
        DAAL = "DAAL", "Daal"
        SALAD = "SALAD", "Salad / raw"
        BEVERAGE = "BEVERAGE", "Beverage"
        SWEET = "SWEET", "Sweet"

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=24, unique=True)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.VEG)
    serving_size_g = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("200"),
        help_text="Standard portion size in grams (one portion)",
    )
    direct_unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Overrides the recipe-derived cost when set",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Dishes"

    def __str__(self) -> str:
        return self.name

    def active_recipe(self, on_date: dt.date | None = None) -> "Recipe | None":
        on_date = on_date or dt.date.today()
        queryset = Recipe.objects.filter(dish=self).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date)
        )
        return queryset.order_by("-effective_from", "-version").first()

    def cost_per_portion(self, on_date: dt.date | None = None, costs: dict | None = None) -> Decimal:
        """What one portion of this dish costs the kitchen.

        The **gross** quantity is used, not the net one. Gross includes the
        trim loss - the peelings, the cleaning, the parts that never reach the
        plate. The kitchen paid for those too, so they belong in the cost of
        the portion. The net quantity is what a student actually eats, and it
        is what the portion size describes.

        ``costs`` is an optional pre-built map of ingredient id to unit cost
        (see :func:`cost_map`). Passing it in turns a query per ingredient
        into one query per batch.
        """
        if self.direct_unit_cost is not None:
            return self.direct_unit_cost
        recipe = self.active_recipe(on_date)
        if recipe is None:
            return Decimal("0")
        return recipe.cost_per_portion(on_date, costs=costs)

    def grams_per_portion(self) -> Decimal:
        return self.serving_size_g


def cost_map(ingredients, on_date: dt.date | None = None, hall=None) -> dict:
    """Unit cost for many ingredients in a single query.

    Returns ``{ingredient_id: Decimal unit_cost}``. A hall-scoped rate wins
    over the campus-wide rate; where neither exists the cost is zero.
    """
    on_date = on_date or dt.date.today()
    ingredient_ids = [ingredient.id for ingredient in ingredients]
    if not ingredient_ids:
        return {}
    rates = (
        CostRate.objects.filter(ingredient_id__in=ingredient_ids, effective_from__lte=on_date)
        .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
        .order_by("-effective_from")
    )
    if hall is not None:
        rates = rates.filter(models.Q(hall=hall) | models.Q(hall__isnull=True))

    campus: dict[int, Decimal] = {}
    scoped: dict[tuple[int, int], Decimal] = {}
    for rate in rates:
        if rate.hall_id is None:
            campus.setdefault(rate.ingredient_id, rate.unit_cost)
        else:
            scoped.setdefault((rate.hall_id, rate.ingredient_id), rate.unit_cost)

    result: dict[int, Decimal] = {}
    for ingredient_id in ingredient_ids:
        if hall is not None and (hall.id, ingredient_id) in scoped:
            result[ingredient_id] = scoped[(hall.id, ingredient_id)]
        else:
            result[ingredient_id] = campus.get(ingredient_id, Decimal("0"))
    return result


class Recipe(TimeStampedModel):
    """Versioned ingredient mapping for a dish."""

    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, related_name="recipes")
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(default=dt.date.today)
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["dish", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["dish", "version"], name="uniq_recipe_dish_version"),
        ]

    def __str__(self) -> str:
        return f"{self.dish.name} (v{self.version})"

    def cost_per_portion(self, on_date: dt.date | None = None, costs: dict | None = None) -> Decimal:
        """What one portion of this dish costs the kitchen.

        Uses the gross quantity (including trim loss), because the money left
        the store for the peelings as well as for the food on the plate.
        """
        on_date = on_date or dt.date.today()
        total = Decimal("0")
        for item in self.items.select_related("ingredient"):
            unit_cost = (
                costs.get(item.ingredient_id, Decimal("0"))
                if costs is not None
                else item.ingredient.unit_cost(on_date)
            )
            total += item.gross_quantity * unit_cost
        return total

    def cost_per_portion_including_trim(self, on_date: dt.date | None = None) -> Decimal:
        on_date = on_date or dt.date.today()
        total = Decimal("0")
        for item in self.items.select_related("ingredient"):
            total += item.gross_quantity * item.ingredient.unit_cost(on_date)
        return total


class RecipeItem(TimeStampedModel):
    """One ingredient inside a recipe: quantity required per portion."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="recipe_items")
    quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0"),
        help_text="Net quantity per portion, in the ingredient's base unit",
    )
    trim_loss_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
        help_text="Unusable share (peeling, cleaning) added on top of the net quantity",
    )

    class Meta:
        ordering = ["recipe", "ingredient"]
        constraints = [
            models.UniqueConstraint(fields=["recipe", "ingredient"], name="uniq_recipe_ingredient"),
        ]

    def __str__(self) -> str:
        return f"{self.recipe.dish.name}: {self.quantity} {self.ingredient.base_unit} {self.ingredient.name}"

    @property
    def gross_quantity(self) -> Decimal:
        """Quantity actually to be bought, including trim loss."""
        factor = (Decimal("100") + self.trim_loss_pct) / Decimal("100")
        return self.quantity * factor


class CostRate(TimeStampedModel):
    """Effective-dated cost of one base unit of an ingredient.

    A null ``hall`` means the rate applies campus-wide; a hall-scoped rate
    overrides it for that hall (contract pricing differences between messes).
    """

    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="cost_rates")
    hall = models.ForeignKey(
        DiningHall, on_delete=models.CASCADE, null=True, blank=True, related_name="cost_rates"
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=4, help_text="Cost of one base unit in rupees"
    )
    effective_from = models.DateField(default=dt.date.today)
    effective_to = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["ingredient", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient", "hall", "effective_from"], name="uniq_cost_rate_scope"
            ),
        ]

    def __str__(self) -> str:
        scope = self.hall.code if self.hall else "campus"
        return f"{self.ingredient.name} @ {scope}: {self.unit_cost}/{self.ingredient.base_unit}"


# ---------------------------------------------------------------------------
# Batch helpers
#
# The application works on a whole service at a time: several dishes, their
# recipes, the recipe lines and the ingredient prices. Fetching each of those
# one at a time is the classic N+1 problem, and it dominates the runtime when
# a twelve-week history is processed service by service. These helpers fetch
# the same data in a fixed number of queries.
# ---------------------------------------------------------------------------

def active_recipes_for(dishes, on_date: dt.date | None = None) -> dict:
    """``{dish_id: Recipe}`` for the active recipe of each dish, in one query."""
    on_date = on_date or dt.date.today()
    dish_ids = [dish.id for dish in dishes]
    if not dish_ids:
        return {}
    recipes = (
        Recipe.objects.filter(
            dish_id__in=dish_ids,
            effective_from__lte=on_date,
            is_active=True,
        )
        .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
        .order_by("dish_id", "-effective_from", "-version")
    )
    result: dict[int, Recipe] = {}
    for recipe in recipes:
        result.setdefault(recipe.dish_id, recipe)
    return result


def recipe_items_for(recipes) -> dict:
    """``{recipe_id: [RecipeItem]}`` for many recipes, in one query."""
    recipe_ids = [recipe.id for recipe in recipes]
    if not recipe_ids:
        return {}
    items: dict[int, list] = {recipe_id: [] for recipe_id in recipe_ids}
    for item in RecipeItem.objects.filter(recipe_id__in=recipe_ids).select_related("ingredient"):
        items[item.recipe_id].append(item)
    return items
