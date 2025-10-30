# models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta, time
from django.core.exceptions import ValidationError

class Center(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)

    def __str__(self):
        return self.name

class Service(models.Model):
    CATEGORY_CHOICES = [
        ('service', 'Service'),
        ('modification', 'Modification'),
    ]
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    duration_minutes = models.PositiveIntegerField()  # e.g., 45 for short service, 240 for 4hr mod
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} ({self.category})"

class Booking(models.Model):
    STATUS_CHOICES = [
        ('booked', 'Booked'),
        ('cancelled', 'Cancelled'),
    ]
    center = models.ForeignKey(Center, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    customer_name = models.CharField(max_length=100)  # Simple; use User in production
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='booked')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['center', 'date', 'start_time', 'end_time']  # Prevent overlaps

    def clean(self):
        # Ensure end_time > start_time
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be after start time.')
        # Compute duration and match service
        duration = (timezone.datetime.combine(self.date, self.end_time) - 
                    timezone.datetime.combine(self.date, self.start_time)).total_seconds() / 60
        if abs(duration - self.service.duration_minutes) > 1:  # Allow 1min tolerance
            raise ValidationError('Duration must match service duration.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_name} - {self.service} at {self.center} on {self.date}"