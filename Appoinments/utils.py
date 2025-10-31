# utils.py (Helper functions for availability)
from datetime import datetime, timedelta,time
from .models import Booking, Center
from django.utils import timezone
from . import utils

BUFFER_MINUTES = 15  # Cleanup buffer

def get_workday_start_end():
    """Assume 9:00 AM to 6:00 PM"""
    return time(9, 0), time(18, 0)

def merge_intervals(intervals):
    """Merge overlapping or adjacent intervals (considering buffer for merging)"""
    if not intervals:
        return []
    
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = []
    
    current_start, current_end = sorted_intervals[0]
    
    for interval in sorted_intervals[1:]:
        interval_start, interval_end = interval
        
        # If intervals overlap or are within buffer, merge them
        if interval_start <= current_end + timedelta(minutes=BUFFER_MINUTES):
            current_end = max(current_end, interval_end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = interval_start, interval_end
    
    merged.append((current_start, current_end))
    return merged

def get_free_intervals(center, date, duration_minutes):
    """Get ALL free intervals between bookings"""
    workday_start_time, workday_end_time = get_workday_start_end()
    workday_start = timezone.datetime.combine(date, workday_start_time)
    workday_end = timezone.datetime.combine(date, workday_end_time)

    # Get all bookings for the day
    bookings = Booking.objects.filter(
        center=center,
        date=date,
        status='booked'
    ).order_by('start_time')

    # If no bookings, entire day is free
    if not bookings.exists():
        max_start = workday_end - timedelta(minutes=duration_minutes)
        return [(workday_start, max_start)]

    free_intervals = []
    
    # Check gap before first booking
    first_booking_start = timezone.datetime.combine(date, bookings[0].start_time)
    if first_booking_start > workday_start:
        free_end = first_booking_start
        free_duration = (free_end - workday_start).total_seconds() / 60
        if free_duration >= duration_minutes:
            max_start = free_end - timedelta(minutes=duration_minutes)
            free_intervals.append((workday_start, max_start))

    # Check gaps between bookings
    for i in range(len(bookings) - 1):
        current_booking_end = timezone.datetime.combine(date, bookings[i].end_time)
        next_booking_start = timezone.datetime.combine(date, bookings[i + 1].start_time)
        
        # Free time between current booking end and next booking start
        if current_booking_end < next_booking_start:
            free_start = current_booking_end
            free_end = next_booking_start
            free_duration = (free_end - free_start).total_seconds() / 60
            
            if free_duration >= duration_minutes:
                max_start = free_end - timedelta(minutes=duration_minutes)
                free_intervals.append((free_start, max_start))

    # Check gap after last booking
    last_booking_end = timezone.datetime.combine(date, bookings.last().end_time)
    if last_booking_end < workday_end:
        free_start = last_booking_end
        free_end = workday_end
        free_duration = (free_end - free_start).total_seconds() / 60
        if free_duration >= duration_minutes:
            max_start = free_end - timedelta(minutes=duration_minutes)
            free_intervals.append((free_start, max_start))

    return free_intervals

def get_possible_slots(center, date, duration_minutes):
    """Generate intelligent time slots based on service duration"""
    gaps = get_free_intervals(center, date, duration_minutes)
    slots = []
    
    # Define slot patterns based on service duration
    if duration_minutes >= 240:  # 4+ hours - major services
        interval_minutes = 240  # 4 hours between slots
        round_to = 60  # Round to nearest hour
    elif duration_minutes >= 60:  # 1-3 hours - standard services
        interval_minutes = 60  # 1 hour between slots
        round_to = 60  # Round to nearest hour
    elif duration_minutes >= 30:  # 30-59 minutes - medium services
        interval_minutes = 60  # 1 hour between slots
        round_to = 60  # Round to nearest hour
    else:  # Under 30 minutes - quick services
        interval_minutes = 30  # 30 minutes between slots
        round_to = 30  # Round to nearest 30 minutes
    
    for gap_start, gap_max_start in gaps:
        current_start = gap_start
        
        # Round to appropriate time boundary
        if round_to == 60:  # Round to hour
            if current_start.minute != 0:
                current_start = current_start.replace(minute=0, second=0, microsecond=0)
                current_start += timedelta(hours=1)
        elif round_to == 30:  # Round to 30 minutes
            minutes = current_start.minute
            if minutes < 30:
                current_start = current_start.replace(minute=0, second=0, microsecond=0)
            else:
                current_start = current_start.replace(minute=30, second=0, microsecond=0)
        
        # Generate slots
        while current_start <= gap_max_start:
            end_time = current_start + timedelta(minutes=duration_minutes)
            
            if end_time.time() <= time(18, 0):  # Within work hours
                remaining_after = (timezone.datetime.combine(date, time(18, 0)) - end_time).total_seconds() / 60
                
                slots.append({
                    'start_time': current_start.time(),
                    'end_time': end_time.time(),
                    'gap_remaining_after': remaining_after
                })
            
            current_start += timedelta(minutes=interval_minutes)
    
    slots.sort(key=lambda x: x['start_time'])
    return slots[:20]

def suggest_alternative_dates(center, service, days_ahead=7):
    """Suggest dates with availability"""
    today = timezone.now().date()
    suggestions = []
    for i in range(1, days_ahead + 1):
        candidate_date = today + timedelta(days=i)
        slots = get_possible_slots(center, candidate_date, service.duration_minutes)
        if slots:
            suggestions.append({
                'date': candidate_date,
                'num_slots': len(slots),
                'earliest_start': slots[0]['start_time'] if slots else None
            })
    # Sort by num_slots descending
    suggestions.sort(key=lambda x: x['num_slots'], reverse=True)
    return suggestions[:3]  # Top 3