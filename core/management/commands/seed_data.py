"""
Management command to seed the Mess Demand Forecasting & Food Waste Platform database
with realistic data for demonstrations and testing.
"""
import random
from datetime import date, timedelta, time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from core.models import User, DiningHall, MealService, CostRate, SystemConfiguration
from menu.models import Ingredient, Dish, Recipe, RecipeItem, Menu, MenuDish, MenuSchedule
from calendar_events.models import CalendarEvent
from forecasting.models import ForecastModel, Forecast
from preparation.models import PreparationPlan, PreparationDish, IngredientIndent, IndentItem
from actuals.models import ServiceActual, DishActual, WasteRecord
from attendance.models import AttendanceRecord, AttendanceSummary


class Command(BaseCommand):
    help = "Populate database with rich demonstration data for mess forecasting and waste tracking"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting database seeding..."))
        with transaction.atomic():
            self.seed_config()
            halls, services = self.seed_core()
            users = self.seed_users(halls)
            ingredients = self.seed_ingredients()
            dishes, recipes = self.seed_dishes_and_recipes(ingredients)
            menus = self.seed_menus(halls, services, dishes, recipes, users['admin'])
            events = self.seed_calendar_events(halls, users['admin'])
            model = self.seed_forecast_model()
            self.seed_historical_and_future_data(halls, services, menus, dishes, recipes, model, users)
        
        self.stdout.write(self.style.SUCCESS("Successfully seeded mess forecasting database!"))

    def seed_config(self):
        configs = [
            ('LOOKBACK_DAYS', '28', 'Number of lookback days for forecasting'),
            ('SAFETY_MARGIN_DEFAULT', '1.10', 'Default safety margin over forecasted demand'),
            ('MAX_OVER_PREPARATION_PCT', '15.0', 'Alert threshold for over-preparation'),
            ('CURRENCY_SYMBOL', '₹', 'Display currency symbol'),
            ('CAMPUS_NAME', 'National Institute of Technology', 'Campus name'),
        ]
        for key, val, desc in configs:
            SystemConfiguration.objects.update_or_create(key=key, defaults={'value': val, 'description': desc})

    def seed_core(self):
        halls_data = [
            {'name': 'Central Dining Hall', 'code': 'CDH', 'capacity': 1200, 'registered_strength': 1050, 'location': 'Block A Campus Center'},
            {'name': 'North Hostel Mess', 'code': 'NHM', 'capacity': 650, 'registered_strength': 550, 'location': 'North Campus Zone 1'},
            {'name': 'South Hostel Mess', 'code': 'SHM', 'capacity': 600, 'registered_strength': 480, 'location': 'South Campus Zone 2'},
        ]
        halls = {}
        for hd in halls_data:
            hall, _ = DiningHall.objects.update_or_create(code=hd['code'], defaults=hd)
            halls[hd['code']] = hall

        services = {}
        service_defs = [
            ('Breakfast', MealService.MealType.BREAKFAST, time(7, 30), time(9, 30), Decimal('1.08')),
            ('Lunch', MealService.MealType.LUNCH, time(12, 0), time(14, 30), Decimal('1.10')),
            ('Snacks', MealService.MealType.SNACKS, time(17, 0), time(18, 30), Decimal('1.05')),
            ('Dinner', MealService.MealType.DINNER, time(19, 30), time(22, 0), Decimal('1.12')),
        ]
        for h_code, hall in halls.items():
            services[h_code] = {}
            for name, mtype, st, et, sm in service_defs:
                service, _ = MealService.objects.update_or_create(
                    dining_hall=hall, meal_type=mtype, start_time=st,
                    defaults={'name': f"{hall.code} {name}", 'end_time': et, 'safety_margin': sm, 'is_active': True}
                )
                services[h_code][mtype] = service

        return halls, services

    def seed_users(self, halls):
        users = {}
        
        # Admin
        admin, _ = User.objects.update_or_create(
            username='admin',
            defaults={
                'first_name': 'Dev',
                'last_name': 'Sharma',
                'email': 'admin@mess.edu',
                'role': User.Role.ADMINISTRATOR,
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin.set_password('admin123')
        admin.save()
        users['admin'] = admin

        # Manager
        manager, _ = User.objects.update_or_create(
            username='manager',
            defaults={
                'first_name': 'Rajesh',
                'last_name': 'Kumar',
                'email': 'manager@mess.edu',
                'role': User.Role.MESS_MANAGER,
                'dining_hall': halls['CDH'],
                'is_staff': True,
            }
        )
        manager.set_password('manager123')
        manager.save()
        users['manager'] = manager

        # Kitchen Staff
        kitchen, _ = User.objects.update_or_create(
            username='kitchen',
            defaults={
                'first_name': 'Ramesh',
                'last_name': 'Patel',
                'email': 'kitchen@mess.edu',
                'role': User.Role.KITCHEN_STAFF,
                'dining_hall': halls['CDH'],
            }
        )
        kitchen.set_password('kitchen123')
        kitchen.save()
        users['kitchen'] = kitchen

        # Students
        students = []
        for i in range(1, 21):
            s, _ = User.objects.update_or_create(
                username=f"student{i}",
                defaults={
                    'first_name': f'Student_{i}',
                    'last_name': 'Gupta',
                    'email': f'student{i}@student.edu',
                    'role': User.Role.STUDENT,
                    'student_id': f"2024CS{100+i:03d}",
                    'rfid_uid': f"E2000019230{i:03d}",
                    'dining_hall': halls['CDH'] if i <= 12 else halls['NHM'],
                }
            )
            s.set_password('student123')
            s.save()
            students.append(s)
        users['students'] = students

        return users

    def seed_ingredients(self):
        items = [
            ('Basmati Rice', 'ING-RICE', 'kg', Decimal('58.00'), 'Grains'),
            ('Whole Wheat Atta', 'ING-ATTA', 'kg', Decimal('38.00'), 'Grains'),
            ('Toor Dal Premium', 'ING-TDAL', 'kg', Decimal('145.00'), 'Pulses'),
            ('Moong Dal Washed', 'ING-MDAL', 'kg', Decimal('125.00'), 'Pulses'),
            ('Fresh Malai Paneer', 'ING-PANR', 'kg', Decimal('350.00'), 'Dairy'),
            ('Farm Fresh Milk', 'ING-MILK', 'L', Decimal('62.00'), 'Dairy'),
            ('Curd / Yogurt', 'ING-CURD', 'kg', Decimal('65.00'), 'Dairy'),
            ('Desi Ghee / Butter', 'ING-GHEE', 'kg', Decimal('580.00'), 'Dairy'),
            ('Refined Sunflower Oil', 'ING-OIL', 'L', Decimal('132.00'), 'Oil & Fats'),
            ('Red Onion', 'ING-ONIN', 'kg', Decimal('34.00'), 'Vegetables'),
            ('Fresh Potato', 'ING-POTA', 'kg', Decimal('24.00'), 'Vegetables'),
            ('Ripe Tomato', 'ING-TOMA', 'kg', Decimal('42.00'), 'Vegetables'),
            ('Green Peas Frozen', 'ING-PEAS', 'kg', Decimal('85.00'), 'Vegetables'),
            ('Cauliflower', 'ING-CAUL', 'kg', Decimal('36.00'), 'Vegetables'),
            ('Ginger Garlic Paste', 'ING-GGPA', 'kg', Decimal('160.00'), 'Spices'),
            ('Garam Masala Blend', 'ING-SPIC', 'kg', Decimal('480.00'), 'Spices'),
            ('Fresh Chicken Breast', 'ING-CHIK', 'kg', Decimal('230.00'), 'Meat'),
            ('Premium Tea Leaves', 'ING-TEA', 'kg', Decimal('310.00'), 'Beverages'),
            ('Refined Sugar', 'ING-SUGR', 'kg', Decimal('44.00'), 'Grocery'),
        ]
        ingredients = {}
        for name, code, unit, cost, cat in items:
            ing, _ = Ingredient.objects.update_or_create(
                code=code,
                defaults={'name': name, 'unit': unit, 'cost_per_unit': cost, 'category': cat, 'is_active': True}
            )
            ingredients[code] = ing
        return ingredients

    def seed_dishes_and_recipes(self, ing):
        dishes_data = [
            ('Dal Tadka', 'DSH-DAL-TADKA', Dish.Category.MAIN, True, False, 200, [
                (ing['ING-TDAL'], Decimal('10.0')), (ing['ING-ONIN'], Decimal('3.0')),
                (ing['ING-TOMA'], Decimal('3.0')), (ing['ING-OIL'], Decimal('1.5')),
                (ing['ING-GGPA'], Decimal('0.8')), (ing['ING-SPIC'], Decimal('0.5')),
            ]),
            ('Paneer Butter Masala', 'DSH-PAN-BTR', Dish.Category.MAIN, True, False, 220, [
                (ing['ING-PANR'], Decimal('12.0')), (ing['ING-TOMA'], Decimal('8.0')),
                (ing['ING-ONIN'], Decimal('4.0')), (ing['ING-GHEE'], Decimal('2.0')),
                (ing['ING-MILK'], Decimal('4.0')), (ing['ING-SPIC'], Decimal('0.8')),
            ]),
            ('Jeera Rice', 'DSH-JRA-RICE', Dish.Category.RICE, True, True, 250, [
                (ing['ING-RICE'], Decimal('15.0')), (ing['ING-OIL'], Decimal('1.0')),
                (ing['ING-SPIC'], Decimal('0.4')),
            ]),
            ('Tawa Chapati', 'DSH-CHAPATI', Dish.Category.BREAD, True, True, 70, [
                (ing['ING-ATTA'], Decimal('6.0')), (ing['ING-OIL'], Decimal('0.5')),
            ]),
            ('Mixed Vegetable Sabzi', 'DSH-MIX-VEG', Dish.Category.MAIN, True, True, 180, [
                (ing['ING-POTA'], Decimal('6.0')), (ing['ING-CAUL'], Decimal('5.0')),
                (ing['ING-PEAS'], Decimal('3.0')), (ing['ING-TOMA'], Decimal('3.0')),
                (ing['ING-OIL'], Decimal('1.2')), (ing['ING-SPIC'], Decimal('0.6')),
            ]),
            ('Murgh Curry (Chicken)', 'DSH-CHK-CURR', Dish.Category.MAIN, False, False, 240, [
                (ing['ING-CHIK'], Decimal('18.0')), (ing['ING-ONIN'], Decimal('6.0')),
                (ing['ING-TOMA'], Decimal('5.0')), (ing['ING-OIL'], Decimal('2.5')),
                (ing['ING-GGPA'], Decimal('1.5')), (ing['ING-SPIC'], Decimal('1.0')),
            ]),
            ('Aloo Poori', 'DSH-POORI-BHAJI', Dish.Category.MAIN, True, True, 220, [
                (ing['ING-ATTA'], Decimal('8.0')), (ing['ING-POTA'], Decimal('10.0')),
                (ing['ING-OIL'], Decimal('4.0')), (ing['ING-SPIC'], Decimal('0.8')),
            ]),
            ('Idli Sambar', 'DSH-IDLI-SMBR', Dish.Category.MAIN, True, True, 200, [
                (ing['ING-RICE'], Decimal('8.0')), (ing['ING-TDAL'], Decimal('4.0')),
                (ing['ING-TOMA'], Decimal('2.0')), (ing['ING-SPIC'], Decimal('0.5')),
            ]),
            ('Gulab Jamun', 'DSH-GLB-JAMN', Dish.Category.DESSERT, True, False, 90, [
                (ing['ING-MILK'], Decimal('8.0')), (ing['ING-ATTA'], Decimal('2.0')),
                (ing['ING-SUGR'], Decimal('10.0')), (ing['ING-GHEE'], Decimal('2.5')),
            ]),
            ('Masala Chai', 'DSH-MSL-CHAI', Dish.Category.BEVERAGE, True, False, 150, [
                (ing['ING-MILK'], Decimal('10.0')), (ing['ING-TEA'], Decimal('1.5')),
                (ing['ING-SUGR'], Decimal('4.0')), (ing['ING-SPIC'], Decimal('0.3')),
            ]),
        ]

        dishes = {}
        recipes = {}
        for name, code, cat, is_veg, is_vegan, portion_grams, items in dishes_data:
            dish, _ = Dish.objects.update_or_create(
                code=code,
                defaults={'name': name, 'category': cat, 'is_vegetarian': is_veg, 'is_vegan': is_vegan, 'is_active': True}
            )
            dishes[code] = dish

            recipe, _ = Recipe.objects.update_or_create(
                dish=dish, name=f"Standard {name} (100p)",
                defaults={'portions': 100, 'portion_size_grams': portion_grams, 'is_default': True, 'preparation_time_minutes': 45}
            )
            recipes[code] = recipe

            for ingredient, qty in items:
                RecipeItem.objects.update_or_create(
                    recipe=recipe, ingredient=ingredient,
                    defaults={'quantity_per_batch': qty}
                )

        return dishes, recipes

    def seed_menus(self, halls, services, dishes, recipes, admin_user):
        menus = {}
        hall = halls['CDH']
        
        # Breakfast Menu
        bf_menu, _ = Menu.objects.update_or_create(
            name="North & South Indian Breakfast",
            dining_hall=hall,
            meal_service=services['CDH'][MealService.MealType.BREAKFAST],
            defaults={'is_published': True, 'created_by': admin_user}
        )
        for i, code in enumerate(['DSH-POORI-BHAJI', 'DSH-IDLI-SMBR', 'DSH-MSL-CHAI']):
            MenuDish.objects.update_or_create(
                menu=bf_menu, dish=dishes[code],
                defaults={'recipe': recipes[code], 'is_main': (i == 0), 'serving_order': i}
            )
        menus['breakfast'] = bf_menu

        # Lunch Menu
        lunch_menu, _ = Menu.objects.update_or_create(
            name="Standard Royal Thali Lunch",
            dining_hall=hall,
            meal_service=services['CDH'][MealService.MealType.LUNCH],
            defaults={'is_published': True, 'created_by': admin_user}
        )
        for i, code in enumerate(['DSH-PAN-BTR', 'DSH-DAL-TADKA', 'DSH-JRA-RICE', 'DSH-CHAPATI', 'DSH-GLB-JAMN']):
            MenuDish.objects.update_or_create(
                menu=lunch_menu, dish=dishes[code],
                defaults={'recipe': recipes[code], 'is_main': (i < 2), 'serving_order': i}
            )
        menus['lunch'] = lunch_menu

        # Dinner Menu
        dinner_menu, _ = Menu.objects.update_or_create(
            name="Dinner Feast & Rotis",
            dining_hall=hall,
            meal_service=services['CDH'][MealService.MealType.DINNER],
            defaults={'is_published': True, 'created_by': admin_user}
        )
        for i, code in enumerate(['DSH-MIX-VEG', 'DSH-DAL-TADKA', 'DSH-CHAPATI', 'DSH-JRA-RICE']):
            MenuDish.objects.update_or_create(
                menu=dinner_menu, dish=dishes[code],
                defaults={'recipe': recipes[code], 'is_main': (i == 0), 'serving_order': i}
            )
        menus['dinner'] = dinner_menu

        return menus

    def seed_calendar_events(self, halls, admin_user):
        today = date.today()
        events_data = [
            ('Mid-Semester Examinations', CalendarEvent.EventType.EXAM, today - timedelta(days=12), today - timedelta(days=5), CalendarEvent.ImpactLevel.HIGH, Decimal('0.82'), 'Library and late night study reduces breakfast/lunch attendance'),
            ('National Festive Holiday', CalendarEvent.EventType.HOLIDAY, today - timedelta(days=18), today - timedelta(days=17), CalendarEvent.ImpactLevel.HIGH, Decimal('0.45'), 'Most hostel students travel home'),
            ('Inter-NIT Sports Meet', CalendarEvent.EventType.SPORTS, today - timedelta(days=3), today - timedelta(days=1), CalendarEvent.ImpactLevel.MEDIUM, Decimal('1.18'), 'Athletes from guest colleges visiting campus dining'),
            ('Tech Fest & Hackathon', CalendarEvent.EventType.CAMPUS_EVENT, today + timedelta(days=3), today + timedelta(days=5), CalendarEvent.ImpactLevel.MEDIUM, Decimal('1.15'), 'High night dinner & breakfast turnout'),
            ('End Semester Exams', CalendarEvent.EventType.EXAM, today + timedelta(days=18), today + timedelta(days=26), CalendarEvent.ImpactLevel.HIGH, Decimal('0.85'), 'Examinations schedule impact'),
        ]
        created = []
        for title, etype, sdate, edate, impact, mult, desc in events_data:
            ev, _ = CalendarEvent.objects.update_or_create(
                title=title, start_date=sdate,
                defaults={
                    'event_type': etype, 'end_date': edate, 'impact_level': impact,
                    'attendance_multiplier': mult, 'description': desc, 'created_by': admin_user
                }
            )
            created.append(ev)
        return created

    def seed_forecast_model(self):
        model, _ = ForecastModel.objects.update_or_create(
            name='Adaptive Weighted Moving Average (WMA-7D)',
            defaults={
                'method': ForecastModel.MethodType.WEIGHTED_MA,
                'lookback_days': 28,
                'weekday_weight': Decimal('0.35'),
                'recency_weight': Decimal('0.45'),
                'event_weight': Decimal('0.20'),
                'current_mape': Decimal('6.85'),
                'description': 'Weighted combination of historical day-of-week averages, recent 7-day trend, and calendar event impact multipliers.',
                'is_active': True,
            }
        )
        return model

    def seed_historical_and_future_data(self, halls, services, menus, dishes, recipes, model, users):
        today = date.today()
        hall = halls['CDH']
        service_lunch = services['CDH'][MealService.MealType.LUNCH]
        service_dinner = services['CDH'][MealService.MealType.DINNER]
        service_bf = services['CDH'][MealService.MealType.BREAKFAST]

        # 30 days history + 7 days future
        all_dates = [today - timedelta(days=d) for d in range(30, 0, -1)] + [today + timedelta(days=d) for d in range(8)]

        random.seed(42)

        for cur_date in all_dates:
            weekday = cur_date.weekday()
            is_future = cur_date > today
            is_past = cur_date < today
            is_today = cur_date == today

            # Schedule menus
            MenuSchedule.objects.update_or_create(
                menu=menus['lunch'], date=cur_date,
                defaults={'is_active': True, 'expected_attendance': 850}
            )

            # Check event multiplier
            event = CalendarEvent.objects.filter(start_date__lte=cur_date, end_date__gte=cur_date).first()
            event_mult = event.attendance_multiplier if event else Decimal('1.00')

            # Base lunch attendance around 820 students with weekday variation
            weekday_factors = [1.02, 1.01, 1.00, 0.98, 0.92, 0.78, 0.75]  # Weekend drops
            base_att = int(850 * weekday_factors[weekday] * float(event_mult))
            noise = random.randint(-25, 25)
            predicted = max(200, base_att + noise)

            # Forecast
            forecast, _ = Forecast.objects.update_or_create(
                meal_service=service_lunch,
                dining_hall=hall,
                date=cur_date,
                defaults={
                    'forecast_model': model,
                    'predicted_attendance': predicted,
                    'lower_bound': max(100, int(predicted * 0.94)),
                    'upper_bound': int(predicted * 1.06),
                    'weekday': weekday,
                    'is_holiday': event.event_type == 'holiday' if event else False,
                    'is_exam_period': event.event_type == 'exam' if event else False,
                    'event_multiplier': event_mult,
                    'historical_avg': Decimal(str(base_att)),
                    'same_weekday_avg': Decimal(str(int(850 * weekday_factors[weekday]))),
                    'data_points_used': 24,
                    'status': Forecast.Status.ACTIVE,
                }
            )

            # Preparation Plan
            safety = Decimal('1.08')
            planned_portions = int(predicted * float(safety))
            plan, _ = PreparationPlan.objects.update_or_create(
                forecast=forecast,
                defaults={
                    'planned_portions': planned_portions,
                    'safety_margin_used': safety,
                    'status': PreparationPlan.Status.COMPLETED if is_past else (PreparationPlan.Status.IN_PROGRESS if is_today else PreparationPlan.Status.APPROVED),
                    'approved_by': users['manager'],
                }
            )

            # Link dishes to preparation plan
            lunch_dish_codes = ['DSH-PAN-BTR', 'DSH-DAL-TADKA', 'DSH-JRA-RICE', 'DSH-CHAPATI', 'DSH-GLB-JAMN']
            for dcode in lunch_dish_codes:
                recipe = recipes[dcode]
                PreparationDish.objects.update_or_create(
                    plan=plan, dish=dishes[dcode],
                    defaults={
                        'recipe': recipe,
                        'portions_to_prepare': planned_portions if dcode != 'DSH-CHAPATI' else planned_portions * 3,
                        'estimated_cost': Decimal(str(round(planned_portions * float(recipe.cost_per_portion), 2))),
                    }
                )

            # Ingredient Indent
            ref_no = f"IND-{cur_date.strftime('%Y%m%d')}-LUNCH"
            indent, _ = IngredientIndent.objects.update_or_create(
                preparation_plan=plan,
                defaults={
                    'reference_number': ref_no,
                    'date_required': cur_date,
                    'status': IngredientIndent.Status.FULFILLED if is_past else IngredientIndent.Status.GENERATED,
                    'total_estimated_cost': Decimal('16500.00'),
                }
            )

            # If past, create ServiceActual and WasteRecord
            if is_past:
                actual_noise = random.randint(-35, 30)
                actual_attendance = max(150, predicted + actual_noise)
                
                # Update forecast with actual attendance & MAPE
                err = abs(predicted - actual_attendance)
                mape = round((err / actual_attendance) * 100, 2)
                forecast.actual_attendance = actual_attendance
                forecast.forecast_error = predicted - actual_attendance
                forecast.mape = Decimal(str(mape))
                forecast.save(update_fields=['actual_attendance', 'forecast_error', 'mape'])

                # Attendance Summary
                AttendanceSummary.objects.update_or_create(
                    dining_hall=hall, meal_service=service_lunch, date=cur_date,
                    defaults={
                        'day_of_week': weekday,
                        'total_scans': actual_attendance + 5,
                        'valid_count': actual_attendance,
                        'manual_count': 8,
                        'duplicate_count': 5,
                        'is_holiday': forecast.is_holiday,
                        'is_exam_period': forecast.is_exam_period,
                        'finalized': True,
                    }
                )

                # Service Actual
                actual, _ = ServiceActual.objects.update_or_create(
                    meal_service=service_lunch, dining_hall=hall, date=cur_date,
                    defaults={
                        'preparation_plan': plan,
                        'actual_attendance': actual_attendance,
                        'recorded_by': users['kitchen'],
                        'is_finalized': True,
                        'finalized_at': timezone.now() - timedelta(days=(today - cur_date).days),
                    }
                )

                # Dish actuals & waste records
                for dcode in lunch_dish_codes:
                    recipe = recipes[dcode]
                    cost_p = recipe.cost_per_portion
                    prepared = planned_portions if dcode != 'DSH-CHAPATI' else planned_portions * 3
                    served = min(prepared, int(actual_attendance * (1.0 if dcode != 'DSH-CHAPATI' else 2.8)))
                    leftover = max(0, prepared - served)
                    waste_kg = round(Decimal(str(leftover * float(recipe.portion_size_grams) / 1000.0)), 2)

                    da, _ = DishActual.objects.update_or_create(
                        service_actual=actual, dish=dishes[dcode],
                        defaults={
                            'recipe': recipe,
                            'portions_prepared': prepared,
                            'portions_served': served,
                            'waste_weight_kg': waste_kg,
                        }
                    )

                    # Waste Record
                    waste_cost = Decimal(str(round(leftover * float(cost_p), 2)))
                    WasteRecord.objects.update_or_create(
                        dish_actual=da,
                        defaults={
                            'service_actual': actual,
                            'dish': dishes[dcode],
                            'date': cur_date,
                            'meal_service': service_lunch,
                            'dining_hall': hall,
                            'portions_wasted': leftover,
                            'weight_wasted_kg': waste_kg,
                            'ingredient_cost_per_portion': cost_p,
                            'total_waste_cost': waste_cost,
                            'over_preparation_cost': waste_cost,
                        }
                    )
