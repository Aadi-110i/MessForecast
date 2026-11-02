"""Attendance views and URLs - high throughput with offline sync"""
import uuid
from datetime import date, timedelta
from django.urls import path
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from attendance.models import AttendanceRecord, AttendanceSummary, QRToken
from attendance.serializers import (
    AttendanceRecordSerializer, AttendanceBulkSyncSerializer,
    AttendanceSummarySerializer, QRTokenSerializer, QRScanSerializer
)
from core.models import MealService


class AttendanceRecordListView(generics.ListAPIView):
    queryset = AttendanceRecord.objects.select_related(
        'student', 'meal_service', 'dining_hall'
    ).filter(is_valid=True)
    serializer_class = AttendanceRecordSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date', 'meal_service', 'dining_hall', 'capture_method']


class AttendanceSummaryListView(generics.ListAPIView):
    queryset = AttendanceSummary.objects.select_related('meal_service', 'dining_hall').all()
    serializer_class = AttendanceSummarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date', 'meal_service', 'dining_hall', 'finalized']


@api_view(['POST'])
def bulk_sync(request):
    """
    Idempotent bulk sync for offline attendance records.
    Accepts array of records with client_uuid; server ignores duplicates.
    Each record carries a client-generated UUID; server ignores one it's already seen.
    """
    serializer = AttendanceBulkSyncSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    result = serializer.save()
    return Response(result, status=status.HTTP_207_MULTI_STATUS)


@api_view(['POST'])
def scan_qr(request):
    """Process a QR code scan at the gate."""
    serializer = QRScanSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    token_str = serializer.validated_data['token']
    device_id = serializer.validated_data.get('device_id', '')
    client_uuid = serializer.validated_data.get('client_uuid') or uuid.uuid4()
    
    try:
        qr_token = QRToken.objects.select_related('student', 'meal_service').get(token=token_str)
    except QRToken.DoesNotExist:
        return Response({'error': 'Invalid QR code'}, status=status.HTTP_404_NOT_FOUND)
    
    if not qr_token.is_valid:
        if qr_token.is_used:
            return Response({'error': 'QR code already used', 'student': str(qr_token.student)}, 
                           status=status.HTTP_409_CONFLICT)
        return Response({'error': 'QR code expired'}, status=status.HTTP_410_GONE)
    
    # Idempotent record creation
    record, created = AttendanceRecord.objects.get_or_create(
        client_uuid=client_uuid,
        defaults={
            'student': qr_token.student,
            'meal_service': qr_token.meal_service,
            'dining_hall': qr_token.meal_service.dining_hall,
            'date': date.today(),
            'scan_time': timezone.now(),
            'capture_method': AttendanceRecord.CaptureMethod.QR,
            'device_id': device_id,
            'sync_status': AttendanceRecord.SyncStatus.SYNCED,
            'synced_at': timezone.now(),
        }
    )
    
    if created:
        qr_token.is_used = True
        qr_token.used_at = timezone.now()
        qr_token.save(update_fields=['is_used', 'used_at'])
    
    return Response({
        'success': True,
        'student': qr_token.student.get_full_name() or qr_token.student.username,
        'student_id': qr_token.student.student_id,
        'meal_service': qr_token.meal_service.name,
        'already_scanned': not created,
        'record_uuid': str(record.client_uuid)
    })


@api_view(['POST'])
def generate_qr_token(request):
    """Generate a QR token for a student."""
    student_id = request.data.get('student_id')
    meal_service_id = request.data.get('meal_service_id')
    
    if not student_id or not meal_service_id:
        return Response({'error': 'student_id and meal_service_id required'}, 
                        status=status.HTTP_400_BAD_REQUEST)
    
    from core.models import User
    try:
        student = User.objects.get(student_id=student_id)
        meal_service = MealService.objects.get(pk=meal_service_id)
    except (User.DoesNotExist, MealService.DoesNotExist) as e:
        return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
    
    # Expire in 5 minutes
    expires = timezone.now() + timedelta(minutes=5)
    token = QRToken.objects.create(
        student=student,
        meal_service=meal_service,
        date=date.today(),
        expires_at=expires,
    )
    
    return Response(QRTokenSerializer(token).data)


@api_view(['GET'])
def attendance_stats(request):
    """Real-time attendance stats for a service."""
    meal_service_id = request.query_params.get('meal_service_id')
    target_date = request.query_params.get('date', str(date.today()))
    
    if not meal_service_id:
        return Response({'error': 'meal_service_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    count = AttendanceRecord.objects.filter(
        meal_service_id=meal_service_id,
        date=target_date,
        is_valid=True,
    ).count()
    
    # Get forecast if available
    try:
        from forecasting.models import Forecast
        forecast = Forecast.objects.get(
            meal_service_id=meal_service_id,
            date=target_date,
            status=Forecast.Status.ACTIVE,
        )
        forecast_value = forecast.predicted_attendance
    except Exception:
        forecast_value = None
    
    return Response({
        'meal_service_id': meal_service_id,
        'date': target_date,
        'current_count': count,
        'forecast': forecast_value,
        'fill_rate': round(count / forecast_value * 100, 1) if forecast_value else None,
    })


urlpatterns = [
    path('', AttendanceRecordListView.as_view(), name='attendance-list'),
    path('summaries/', AttendanceSummaryListView.as_view(), name='attendance-summary-list'),
    path('bulk-sync/', bulk_sync, name='attendance-bulk-sync'),
    path('scan-qr/', scan_qr, name='scan-qr'),
    path('generate-qr/', generate_qr_token, name='generate-qr'),
    path('stats/', attendance_stats, name='attendance-stats'),
]
