"""
Attendance app models: AttendanceRecord with offline sync support
"""
import uuid
from django.db import models
from django.utils import timezone


class AttendanceRecord(models.Model):
    """
    Single meal attendance record per student per service.
    Supports offline capture with client-generated UUID for idempotent sync.
    """
    
    class CaptureMethod(models.TextChoices):
        QR = 'qr', 'QR Code Scan'
        RFID = 'rfid', 'RFID Card'
        MANUAL = 'manual', 'Manual Entry'
        BIOMETRIC = 'biometric', 'Biometric'
    
    class SyncStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Sync'
        SYNCED = 'synced', 'Synced'
        CONFLICT = 'conflict', 'Conflict'
    
    # Idempotency key: client generates UUID offline, server ignores duplicates
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True,
                                    help_text='Client-generated UUID for offline sync idempotency')
    
    student = models.ForeignKey(
        'core.User', on_delete=models.CASCADE, related_name='attendance_records',
        null=True, blank=True
    )
    student_id_str = models.CharField(max_length=50, blank=True,
                                       help_text='Fallback if student FK not resolved')
    
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='attendance_records'
    )
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='attendance_records'
    )
    
    date = models.DateField(db_index=True)
    scan_time = models.DateTimeField(default=timezone.now)
    
    capture_method = models.CharField(
        max_length=20, choices=CaptureMethod.choices, default=CaptureMethod.QR
    )
    device_id = models.CharField(max_length=100, blank=True, 
                                  help_text='Scanner device identifier')
    
    sync_status = models.CharField(
        max_length=20, choices=SyncStatus.choices, default=SyncStatus.SYNCED
    )
    synced_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    is_valid = models.BooleanField(default=True, 
                                    help_text='False if duplicate or invalid')
    invalidation_reason = models.CharField(max_length=200, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'attendance_record'
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
        indexes = [
            models.Index(fields=['date', 'meal_service', 'dining_hall']),
            models.Index(fields=['date', 'student']),
            models.Index(fields=['dining_hall', 'date']),
        ]
        constraints = [
            # One valid record per student per meal service per date
            models.UniqueConstraint(
                fields=['student', 'meal_service', 'date'],
                condition=models.Q(is_valid=True),
                name='unique_valid_attendance'
            )
        ]
    
    def __str__(self):
        student_label = str(self.student) if self.student else self.student_id_str
        return f"{student_label} - {self.meal_service.name} on {self.date}"
    
    def save(self, *args, **kwargs):
        # Auto-populate dining hall from meal service if not set
        if not self.dining_hall_id and self.meal_service_id:
            self.dining_hall = self.meal_service.dining_hall
        super().save(*args, **kwargs)


class AttendanceSummary(models.Model):
    """
    Aggregated daily attendance count per meal service.
    Updated by signal/task after each service window closes.
    """
    
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE, related_name='summaries'
    )
    dining_hall = models.ForeignKey(
        'core.DiningHall', on_delete=models.CASCADE, related_name='attendance_summaries'
    )
    date = models.DateField()
    
    total_scans = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    manual_count = models.PositiveIntegerField(default=0)
    
    # Computed features for forecasting
    is_holiday = models.BooleanField(default=False)
    is_exam_period = models.BooleanField(default=False)
    is_event_day = models.BooleanField(default=False)
    day_of_week = models.PositiveSmallIntegerField(
        help_text='0=Monday, 6=Sunday'
    )
    week_of_month = models.PositiveSmallIntegerField(default=1)
    
    finalized = models.BooleanField(default=False,
                                     help_text='True once service window is closed')
    finalized_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendance_summary'
        verbose_name = 'Attendance Summary'
        verbose_name_plural = 'Attendance Summaries'
        unique_together = ['meal_service', 'dining_hall', 'date']
        ordering = ['-date', 'meal_service']
    
    def __str__(self):
        return f"{self.dining_hall.name} - {self.meal_service.name} - {self.date}: {self.valid_count}"


class QRToken(models.Model):
    """Temporary QR code token for attendance scanning."""
    
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    student = models.ForeignKey(
        'core.User', on_delete=models.CASCADE, related_name='qr_tokens'
    )
    meal_service = models.ForeignKey(
        'core.MealService', on_delete=models.CASCADE
    )
    date = models.DateField()
    
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'attendance_qr_token'
        verbose_name = 'QR Token'
        verbose_name_plural = 'QR Tokens'
    
    def __str__(self):
        return f"QR Token for {self.student.username} - {self.date}"
    
    @property
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
