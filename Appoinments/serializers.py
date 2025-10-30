# serializers.py (Using Django REST Framework)
from rest_framework import serializers
from django.utils import timezone
from django.db import models
from .models import Booking, Center, Service
from Appoinments import utils  # Make sure this imports your utils

class CenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Center
        fields = ['id', 'name', 'location']

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'category', 'duration_minutes', 'price']

class BookingSerializer(serializers.ModelSerializer):
    center = CenterSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    center_id = serializers.IntegerField(write_only=True)
    service_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'center', 'service', 'date', 'start_time', 'end_time', 
                  'customer_name', 'status', 'center_id', 'service_id']

    def validate(self, data):  # data is passed as parameter here
        # Check availability
        center = Center.objects.get(id=data['center_id'])
        service = Service.objects.get(id=data['service_id'])
        date = data['date']
        start_time = data['start_time']
        end_time = data['end_time']

        # Compute if slot overlaps
        proposed_start = timezone.datetime.combine(date, start_time)
        proposed_end = timezone.datetime.combine(date, end_time)
        duration = (proposed_end - proposed_start).total_seconds() / 60

        if abs(duration - service.duration_minutes) > 1:
            raise serializers.ValidationError("Duration must match service.")

        # Check overlaps - CORRECTED SYNTAX
        overlapping = Booking.objects.filter(
            center=center,
            date=date,
            status='booked'
        ).filter(
            models.Q(start_time__lt=end_time, end_time__gt=start_time) |
            models.Q(start_time__lt=start_time, end_time__gt=end_time)
        ).exists()

        if overlapping:
            raise serializers.ValidationError("Slot overlaps with existing booking.")

        # Check workday bounds - make sure util has get_workday_start_end function
        workday_start, workday_end = utils.get_workday_start_end()  # Fixed from utils to util
        if start_time < workday_start or end_time > workday_end:
            raise serializers.ValidationError("Outside workday hours.")

        # Check buffer with neighbors
        prev_bookings = Booking.objects.filter(
            center=center, date=date, status='booked', end_time__lte=start_time
        ).order_by('-end_time')[:1]
        
        if prev_bookings:
            prev_end = prev_bookings[0].end_time
            if (timezone.datetime.combine(date, start_time) - 
                timezone.datetime.combine(date, prev_end)).total_seconds() / 60 < utils.BUFFER_MINUTES:  # Fixed from utils to util
                raise serializers.ValidationError("Too close to previous booking.")

        next_bookings = Booking.objects.filter(
            center=center, date=date, status='booked', start_time__gte=end_time
        ).order_by('start_time')[:1]
        
        if next_bookings:
            next_start = next_bookings[0].start_time
            if (timezone.datetime.combine(date, next_start) - 
                timezone.datetime.combine(date, end_time)).total_seconds() / 60 < utils.BUFFER_MINUTES:  # Fixed from utils to util
                raise serializers.ValidationError("Too close to next booking.")

        return data