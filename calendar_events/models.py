"""
Calendar events app models: CalendarEvent (holidays, exams, campus events)
"""
from django.db import models


class CalendarEvent(models.Model):
    """Academic calendar events that affect mess attendance."""
    
    class EventType(models.TextChoices):
        HOLIDAY = 'holiday', 'Public Holiday'
        EXAM = 'exam', 'Examination'
        VACATION = 'vacation', 'Vacation/Break'
        CAMPUS_EVENT = 'campus_event', 'Campus Event'
        SPORTS = 'sports', 'Sports Event'
        CULTURAL = 'cultural', 'Cultural Event'
        TECHNICAL = 'technical', 'Technical Event/Fest'
        OTHER = 'other', 'Other'
    
    class ImpactLevel(models.TextChoices):
        HIGH = 'high', 'High Impact'      # >20% attendance change expected
        MEDIUM = 'medium', 'Medium Impact'  # 10-20% change
        LOW = 'low', 'Low Impact'          # <10% change
    
    title = models.CharField(max_length=300)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    
    # Impact settings for forecasting
    impact_level = models.CharField(
        max_length=10, choices=ImpactLevel.choices, default=ImpactLevel.MEDIUM
    )
    attendance_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=1.00,
        help_text='Expected attendance as fraction of normal (0.5 = 50%, 1.2 = 120%)'
    )
    
    # Affected dining halls (empty = all halls)
    affected_halls = models.ManyToManyField(
        'core.DiningHall', blank=True, related_name='calendar_events'
    )
    
    # Affected meal services (empty = all services)
    affects_breakfast = models.BooleanField(default=True)
    affects_lunch = models.BooleanField(default=True)
    affects_dinner = models.BooleanField(default=True)
    
    description = models.TextField(blank=True)
    source = models.CharField(max_length=200, blank=True,
                               help_text='e.g., Academic calendar, admin notification')
    is_recurring = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, 
        related_name='created_events'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendar_event'
        verbose_name = 'Calendar Event'
        verbose_name_plural = 'Calendar Events'
        ordering = ['start_date']
    
    def __str__(self):
        return f"{self.title} ({self.start_date} to {self.end_date})"
    
    def affects_date(self, date):
        return self.start_date <= date <= self.end_date
    
    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1
