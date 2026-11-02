"""Calendar events views and URLs"""
from django.urls import path
from rest_framework import generics
from rest_framework.serializers import ModelSerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response
from calendar_events.models import CalendarEvent


class CalendarEventSerializer(ModelSerializer):
    event_type_display = lambda self, obj: obj.get_event_type_display()
    
    class Meta:
        model = CalendarEvent
        fields = '__all__'


class CalendarEventListCreateView(generics.ListCreateAPIView):
    queryset = CalendarEvent.objects.prefetch_related('affected_halls').order_by('start_date')
    serializer_class = CalendarEventSerializer
    filterset_fields = ['event_type', 'impact_level']


class CalendarEventDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CalendarEvent.objects.all()
    serializer_class = CalendarEventSerializer


@api_view(['GET'])
def events_for_date_range(request):
    """Get events overlapping a date range."""
    from datetime import date, timedelta
    start = request.query_params.get('start', str(date.today()))
    end = request.query_params.get('end', str(date.today() + timedelta(days=30)))
    
    events = CalendarEvent.objects.filter(
        start_date__lte=end,
        end_date__gte=start,
    )
    serializer = CalendarEventSerializer(events, many=True)
    return Response(serializer.data)


urlpatterns = [
    path('events/', CalendarEventListCreateView.as_view(), name='calendar-event-list'),
    path('events/<int:pk>/', CalendarEventDetailView.as_view(), name='calendar-event-detail'),
    path('events/range/', events_for_date_range, name='calendar-events-range'),
]
