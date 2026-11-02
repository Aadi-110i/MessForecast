"""
Core serializers: User, DiningHall, MealService
"""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from core.models import User, DiningHall, MealService, CostRate, SystemConfiguration


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'role_display', 'student_id', 'phone',
            'dining_hall', 'rfid_uid', 'mess_category',
            'is_active', 'is_active_student', 'date_joined'
        ]
        read_only_fields = ['id', 'date_joined']
        extra_kwargs = {'password': {'write_only': True}}
    
    def get_role_display(self, obj):
        return obj.get_role_display()


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'first_name', 'last_name',
            'role', 'student_id', 'phone', 'dining_hall', 'mess_category'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class DiningHallSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiningHall
        fields = [
            'id', 'name', 'code', 'capacity', 'location',
            'is_active', 'registered_strength', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MealServiceSerializer(serializers.ModelSerializer):
    dining_hall_name = serializers.SerializerMethodField()
    meal_type_display = serializers.SerializerMethodField()
    
    class Meta:
        model = MealService
        fields = [
            'id', 'name', 'meal_type', 'meal_type_display',
            'dining_hall', 'dining_hall_name',
            'start_time', 'end_time', 'is_active',
            'safety_margin', 'max_over_preparation_pct',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_type_display(self, obj):
        return obj.get_meal_type_display()


class CostRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostRate
        fields = '__all__'


class SystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfiguration
        fields = '__all__'
