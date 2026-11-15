"""Master data for the demonstration seed.

This is a fictional but realistic Indian residential-campus mess: two halls,
about twenty dishes with real recipes, three menu cycles that rotate through
the week, and a calendar with exams, a festival and a vacation.

Prices are illustrative rupee rates per base unit, in the region a campus
kitchen actually pays. They exist so the waste costing produces meaningful
numbers, not because they are a market quote.
"""

from __future__ import annotations

from decimal import Decimal

# ---------------------------------------------------------------------------
# Dining halls
# ---------------------------------------------------------------------------
HALLS = [
    {
        "code": "NORTH",
        "name": "North Block Mess",
        "location": "North Block, ground floor",
        "capacity": 700,
        "registered_strength": 620,
        "notes": "Main residential hall. Lunch is the heaviest service of the day.",
    },
    {
        "code": "SOUTH",
        "name": "South Block Mess",
        "location": "South Block, first floor",
        "capacity": 500,
        "registered_strength": 430,
        "notes": "Postgraduate students. Smaller, steadier demand.",
    },
]

# ---------------------------------------------------------------------------
# Ingredients: code, name, base unit, cost per base unit (Rs), pack size
# ---------------------------------------------------------------------------
INGREDIENTS = [
    ("RICE", "Rice", "kg", "45", "25", "Grain"),
    ("FLOUR", "Wheat Flour", "kg", "38", "25", "Grain"),
    ("SOJI", "Semolina", "kg", "48", "25", "Grain"),
    ("DAL_TOOR", "Toor Dal", "kg", "135", "25", "Pulse"),
    ("DAL_MOONG", "Moong Dal", "kg", "145", "25", "Pulse"),
    ("DAL_CHANA", "Chana Dal", "kg", "128", "25", "Pulse"),
    ("POTATO", "Potatoes", "kg", "28", "50", "Vegetable"),
    ("ONION", "Onions", "kg", "32", "40", "Vegetable"),
    ("TOMATO", "Tomatoes", "kg", "40", "30", "Vegetable"),
    ("VEG_MIX", "Mixed Vegetables", "kg", "45", "20", "Vegetable"),
    ("CAULI", "Cauliflower", "kg", "35", "15", "Vegetable"),
    ("PEAS", "Green Peas", "kg", "60", "10", "Vegetable"),
    ("CABBAGE", "Cabbage", "kg", "25", "25", "Vegetable"),
    ("BEANS", "French Beans", "kg", "55", "10", "Vegetable"),
    ("OIL", "Cooking Oil", "l", "145", "15", "Fat"),
    ("GHEE", "Ghee", "kg", "620", "5", "Fat"),
    ("CHICKEN", "Chicken", "kg", "260", "5", "Protein"),
    ("PANEER", "Paneer", "kg", "330", "5", "Protein"),
    ("CURD", "Curd", "kg", "70", "10", "Dairy"),
    ("MILK", "Milk", "l", "58", "10", "Dairy"),
    ("SUGAR", "Sugar", "kg", "52", "25", "Dry"),
    ("TEA", "Tea", "g", "0.85", "250", "Dry"),
    ("SALT", "Salt", "kg", "18", "25", "Spice"),
    ("TURMERIC", "Turmeric Powder", "kg", "220", "5", "Spice"),
    ("CHILLI", "Chilli Powder", "kg", "190", "5", "Spice"),
    ("BANANA", "Banana", "piece", "6", "60", "Fruit"),
]

# ---------------------------------------------------------------------------
# Dishes: code, name, category, serving size (g), recipe lines
#   recipe line = (ingredient code, quantity per portion, trim loss %)
# ---------------------------------------------------------------------------
DISHES = [
    ("POHA", "Poha", "STAPLE", "200", [
        ("RICE", "0.080", "0"), ("ONION", "0.030", "5"), ("POTATO", "0.050", "10"),
        ("OIL", "0.005", "0"), ("TURMERIC", "0.0010", "0"), ("SALT", "0.002", "0"),
    ]),
    ("UPMA", "Upma", "STAPLE", "200", [
        ("FLOUR", "0.090", "0"), ("ONION", "0.030", "5"), ("PEAS", "0.020", "0"),
        ("OIL", "0.006", "0"), ("SALT", "0.002", "0"),
    ]),
    ("IDLI", "Idli", "STAPLE", "150", [
        ("RICE", "0.060", "0"), ("DAL_MOONG", "0.020", "0"), ("SALT", "0.002", "0"),
        ("OIL", "0.003", "0"),
    ]),
    ("SAMBAR", "Sambar", "VEG", "200", [
        ("DAL_TOOR", "0.060", "0"), ("VEG_MIX", "0.050", "10"), ("TOMATO", "0.030", "10"),
        ("OIL", "0.004", "0"), ("TURMERIC", "0.0010", "0"),
    ]),
    ("BANANA_MILK", "Banana and Milk", "BEVERAGE", "250", [
        ("BANANA", "1", "0"), ("MILK", "0.200", "0"),
    ]),
    ("TEA", "Tea", "BEVERAGE", "150", [
        ("TEA", "2.0", "0"), ("MILK", "0.050", "0"), ("SUGAR", "0.012", "0"),
    ]),
    ("RICE_DISH", "Steamed Rice", "STAPLE", "200", [
        ("RICE", "0.180", "0"), ("SALT", "0.002", "0"), ("GHEE", "0.005", "0"),
    ]),
    ("CHAPATI", "Chapati", "STAPLE", "90", [
        ("FLOUR", "0.090", "0"), ("OIL", "0.004", "0"), ("SALT", "0.002", "0"),
    ]),
    ("DAL_TADKA", "Dal Tadka", "DAAL", "200", [
        ("DAL_TOOR", "0.070", "0"), ("TOMATO", "0.030", "10"), ("ONION", "0.020", "10"),
        ("GHEE", "0.004", "0"), ("TURMERIC", "0.0010", "0"),
    ]),
    ("VEG_CURRY", "Mixed Vegetable Curry", "VEG", "200", [
        ("VEG_MIX", "0.120", "10"), ("ONION", "0.020", "10"), ("TOMATO", "0.030", "10"),
        ("OIL", "0.006", "0"), ("CHILLI", "0.0010", "0"),
    ]),
    ("ALOO_GOBI", "Aloo Gobi", "VEG", "200", [
        ("POTATO", "0.080", "10"), ("CAULI", "0.070", "15"), ("ONION", "0.020", "10"),
        ("OIL", "0.005", "0"), ("CHILLI", "0.0010", "0"),
    ]),
    ("CHANA_CURRY", "Chana Masala", "VEG", "200", [
        ("DAL_CHANA", "0.070", "0"), ("TOMATO", "0.040", "10"), ("ONION", "0.020", "10"),
        ("OIL", "0.005", "0"), ("CHILLI", "0.0010", "0"),
    ]),
    ("PANEER_CURRY", "Paneer Curry", "VEG", "200", [
        ("PANEER", "0.080", "0"), ("ONION", "0.030", "10"), ("TOMATO", "0.030", "10"),
        ("GHEE", "0.004", "0"), ("CHILLI", "0.0010", "0"),
    ]),
    ("CHICKEN_CURRY", "Chicken Curry", "NONVEG", "200", [
        ("CHICKEN", "0.120", "0"), ("ONION", "0.030", "10"), ("TOMATO", "0.030", "10"),
        ("OIL", "0.005", "0"), ("CHILLI", "0.0010", "0"),
    ]),
    ("SALAD", "Salad", "SALAD", "120", [
        ("CABBAGE", "0.050", "15"), ("TOMATO", "0.030", "10"), ("ONION", "0.010", "10"),
    ]),
    ("CURD_DISH", "Curd", "DAAL", "150", [("CURD", "0.150", "0")]),
    ("KHICHDI", "Khichdi", "STAPLE", "250", [
        ("RICE", "0.100", "0"), ("DAL_TOOR", "0.040", "0"), ("GHEE", "0.004", "0"),
        ("SALT", "0.002", "0"),
    ]),
    ("FRY_RICE", "Fried Rice", "STAPLE", "200", [
        ("RICE", "0.160", "0"), ("VEG_MIX", "0.050", "10"), ("OIL", "0.006", "0"),
    ]),
    ("RAITA", "Raita", "DAAL", "150", [
        ("CURD", "0.120", "0"), ("ONION", "0.010", "10"), ("CHILLI", "0.0005", "0"),
    ]),
    ("PATTY", "Vegetable Patty", "VEG", "100", [
        ("SOJI", "0.045", "0"), ("VEG_MIX", "0.040", "10"), ("OIL", "0.008", "0"),
        ("CHILLI", "0.0005", "0"),
    ]),
]

# ---------------------------------------------------------------------------
# Menu cycles: code, name, and the dishes served at each meal
# ---------------------------------------------------------------------------
MENUS = [
    {
        "code": "MENU_A",
        "name": "Menu Cycle A",
        "cycle_label": "Week A",
        "description": "Light veg cycle with paneer on the dinner turn.",
        "items": {
            "BREAKFAST": ["POHA", "IDLI", "SAMBAR", "BANANA_MILK"],
            "LUNCH": ["RICE_DISH", "CHAPATI", "DAL_TADKA", "VEG_CURRY", "SALAD"],
            "DINNER": ["CHAPATI", "DAL_TADKA", "PANEER_CURRY", "CURD_DISH"],
        },
    },
    {
        "code": "MENU_B",
        "name": "Menu Cycle B",
        "cycle_label": "Week B",
        "description": "Chana and aloo gobi with chicken at dinner.",
        "items": {
            "BREAKFAST": ["UPMA", "IDLI", "SAMBAR", "BANANA_MILK"],
            "LUNCH": ["RICE_DISH", "CHAPATI", "CHANA_CURRY", "ALOO_GOBI", "SALAD"],
            "DINNER": ["KHICHDI", "DAL_TADKA", "CHICKEN_CURRY", "RAITA"],
        },
    },
    {
        "code": "MENU_C",
        "name": "Menu Cycle C",
        "cycle_label": "Week C",
        "description": "Chicken at lunch, vegetable patty at dinner.",
        "items": {
            "BREAKFAST": ["POHA", "TEA", "BANANA_MILK"],
            "LUNCH": ["RICE_DISH", "CHAPATI", "DAL_TADKA", "CHICKEN_CURRY", "SALAD"],
            "DINNER": ["CHAPATI", "VEG_CURRY", "PATTY", "CURD_DISH"],
        },
    },
]

# ---------------------------------------------------------------------------
# How popular each dish is, relative to the others on the same menu.
# These are the "truth" the system has to learn from the actuals.
# ---------------------------------------------------------------------------
DISH_POPULARITY = {
    "RICE_DISH": 1.00, "CHAPATI": 0.58, "DAL_TADKA": 0.58, "VEG_CURRY": 0.34,
    "SALAD": 0.13, "CURD_DISH": 0.32, "PANEER_CURRY": 0.68, "CHICKEN_CURRY": 0.72,
    "ALOO_GOBI": 0.40, "CHANA_CURRY": 0.42, "KHICHDI": 0.55, "RAITA": 0.30,
    "POHA": 0.85, "UPMA": 0.60, "IDLI": 0.55, "SAMBAR": 0.50, "BANANA_MILK": 0.45,
    "TEA": 0.40, "FRY_RICE": 0.65, "PATTY": 0.35,
}

# ---------------------------------------------------------------------------
# Calendar. Offsets are days back from the end of the history window.
# ---------------------------------------------------------------------------
EVENTS = [
    {
        "name": "Mid-Semester Examinations",
        "event_type": "EXAM",
        "offset_start": -62, "offset_end": -49,
        "impact_factor": "1.250", "meals": "", "description": "Students stay on campus and eat at set times.",
    },
    {
        "name": "Republic Day Holiday",
        "event_type": "HOLIDAY",
        "offset_start": -70, "offset_end": -70,
        "impact_factor": "0.250", "meals": "", "description": "Public holiday. The mess runs at reduced demand.",
    },
    {
        "name": "Technical Festival",
        "event_type": "FEST",
        "offset_start": -44, "offset_end": -42,
        "impact_factor": "1.220", "meals": "LUNCH,DINNER",
        "description": "Three days of events with guest speakers and visitors.",
    },
    {
        "name": "Public Holiday",
        "event_type": "HOLIDAY",
        "offset_start": -33, "offset_end": -33,
        "impact_factor": "0.250", "meals": "", "description": "Campus holiday.",
    },
    {
        "name": "Annual Sports Day",
        "event_type": "SPORTS",
        "offset_start": -30, "offset_end": -30,
        "impact_factor": "1.350", "meals": "",
        "description": "Whole campus eats together in the afternoon.",
    },
    {
        "name": "End-Semester Examinations",
        "event_type": "EXAM",
        "offset_start": -25, "offset_end": -14,
        "impact_factor": "1.300", "meals": "",
        "description": "The heaviest demand period of the term.",
    },
    {
        "name": "Winter Vacation",
        "event_type": "VACATION",
        "offset_start": -12, "offset_end": -4,
        "impact_factor": "0.300", "meals": "",
        "description": "Most students have gone home. The mess serves a reduced roll.",
    },
]

# ---------------------------------------------------------------------------
# Demand shape
# ---------------------------------------------------------------------------
#: Share of registered strength that turns up, by meal.
MEAL_ATTENDANCE_RATE = {
    "BREAKFAST": "0.42",
    "LUNCH": "0.78",
    "DINNER": "0.68",
}

#: Monday to Sunday.
WEEKDAY_MULTIPLIER = {
    0: "0.92", 1: "0.94", 2: "0.95", 3: "0.97",
    4: "1.08", 5: "1.12", 6: "1.05",
}

#: Portions of food a student takes in a meal.
PORTIONS_PER_STUDENT = {
    "BREAKFAST": "1.60",
    "LUNCH": "2.60",
    "DINNER": "2.30",
}

#: How much the kitchen used to cook above what was needed, before the
#: platform existed. This is the waste the project is trying to remove.
BASELINE_OVERPREPARATION = "1.16"

#: The margin the forecast-driven plan allows.
LIVE_OVERPREPARATION_PCT = "8.00"

# ---------------------------------------------------------------------------
# Demonstration accounts
# ---------------------------------------------------------------------------
DEMO_USERS = [
    ("manager", "MESS_MANAGER", "Meera", "Rao", None),
    ("chef", "KITCHEN_STAFF", "Suresh", "Kumar", "NORTH"),
    ("chef2", "KITCHEN_STAFF", "Lata", "Joshi", "SOUTH"),
    ("admin", "MESS_ADMIN", "Anil", "Verma", None),
    ("finance", "FINANCE_OFFICER", "Priya", "Nair", None),
    ("sysadmin", "ADMINISTRATOR", "System", "Administrator", None),
    ("student", "STUDENT", "Ravi", "Kumar", None),
]

DEMO_PASSWORD = "messdemo"
