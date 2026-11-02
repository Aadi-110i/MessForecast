"""Lightweight serializers to avoid circular imports in analytics dashboard"""
from rest_framework import serializers
from forecasting.models import Forecast


class ForecastLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forecast
        fields = ['id', 'date', 'predicted_attendance', 'lower_bound', 'upper_bound', 'status']
