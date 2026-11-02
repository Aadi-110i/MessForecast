"""
Attendance serializers - supports offline sync with client UUID
"""
import uuid
from rest_framework import serializers
from attendance.models import AttendanceRecord, AttendanceSummary, QRToken
from django.utils import timezone


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'client_uuid', 'student', 'student_name', 'student_id_str',
            'meal_service', 'dining_hall', 'date', 'scan_time',
            'capture_method', 'device_id', 'sync_status',
            'is_valid', 'invalidation_reason', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_valid', 'invalidation_reason']
    
    def get_student_name(self, obj):
        if obj.student:
            return obj.student.get_full_name() or obj.student.username
        return obj.student_id_str


class AttendanceBulkSyncSerializer(serializers.Serializer):
    """
    Bulk sync endpoint for offline attendance records.
    Accepts an array of records; server ignores duplicates by client_uuid.
    """
    records = AttendanceRecordSerializer(many=True)
    device_id = serializers.CharField(max_length=100, required=False, default='')
    
    def create(self, validated_data):
        records_data = validated_data['records']
        device_id = validated_data.get('device_id', '')
        
        created = []
        skipped = []
        errors = []
        
        for record_data in records_data:
            client_uuid = record_data.get('client_uuid') or uuid.uuid4()
            try:
                # Idempotent: unique constraint on client_uuid means duplicates are ignored
                record, was_created = AttendanceRecord.objects.get_or_create(
                    client_uuid=client_uuid,
                    defaults={**record_data, 'device_id': device_id or record_data.get('device_id', ''),
                               'sync_status': AttendanceRecord.SyncStatus.SYNCED,
                               'synced_at': timezone.now()}
                )
                if was_created:
                    created.append(str(client_uuid))
                else:
                    skipped.append(str(client_uuid))
            except Exception as e:
                errors.append({'uuid': str(client_uuid), 'error': str(e)})
        
        return {'created': len(created), 'skipped': len(skipped), 'errors': errors}


class QRTokenSerializer(serializers.ModelSerializer):
    qr_data = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = QRToken
        fields = [
            'id', 'token', 'student', 'meal_service', 'date',
            'is_used', 'used_at', 'expires_at', 'qr_data', 'is_valid', 'created_at'
        ]
        read_only_fields = ['id', 'token', 'created_at']
    
    def get_qr_data(self, obj):
        return str(obj.token)
    
    def get_is_valid(self, obj):
        return obj.is_valid


class AttendanceSummarySerializer(serializers.ModelSerializer):
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AttendanceSummary
        fields = [
            'id', 'meal_service', 'meal_service_name',
            'dining_hall', 'dining_hall_name', 'date',
            'total_scans', 'valid_count', 'duplicate_count', 'manual_count',
            'is_holiday', 'is_exam_period', 'is_event_day',
            'day_of_week', 'week_of_month', 'finalized',
            'created_at', 'updated_at'
        ]
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.meal_service.name


class QRScanSerializer(serializers.Serializer):
    """For scanning a QR token at the gate."""
    token = serializers.UUIDField()
    device_id = serializers.CharField(max_length=100, required=False, default='')
    client_uuid = serializers.UUIDField(required=False)
