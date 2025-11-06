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
    """Generate slots with dynamic intervals based on service type"""
    gaps = get_free_intervals(center, date, duration_minutes)
    slots = []
    
    # Calculate optimal interval considering buffer and efficiency
    interval_minutes = max(duration_minutes, calculate_optimal_interval(duration_minutes))
    
    # Determine rounding based on service duration
    if duration_minutes >= 60:
        round_to = 60
    elif duration_minutes >= 30:
        round_to = 30
    else:
        round_to = 15
    
    for gap_start, gap_max_start in gaps:
        current_start = gap_start
        
        # Round start time
        current_start = round_time(current_start, round_to)
        
        while current_start <= gap_max_start:
            end_time = current_start + timedelta(minutes=duration_minutes)
            
            if end_time.time() <= time(18, 0):
                slots.append({
                    'start_time': current_start.time(),
                    'end_time': end_time.time(),
                    'gap_remaining_after': (timezone.datetime.combine(date, time(18, 0)) - end_time).total_seconds() / 60
                })
            
            current_start += timedelta(minutes=interval_minutes)
    
    slots.sort(key=lambda x: x['start_time'])
    return slots[:20]

def calculate_optimal_interval(duration_minutes):
    """Calculate optimal slot interval based on service duration"""
    if duration_minutes >= 240:
        return 240  # Major services - half day apart
    elif duration_minutes >= 120:
        return 120  # Lengthy services - 2 hours apart
    elif duration_minutes >= 60:
        return 60   # Standard services - hourly
    elif duration_minutes >= 30:
        return 45   # Quick services - 45 min intervals
    else:
        return 30   # Express services - 30 min intervals

def round_time(dt, round_to):
    """Round datetime to nearest interval"""
    minutes = dt.minute
    if round_to == 60:
        if minutes >= 30:
            return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            return dt.replace(minute=0, second=0, microsecond=0)
    elif round_to == 30:
        if minutes < 15:
            return dt.replace(minute=0, second=0, microsecond=0)
        elif minutes < 45:
            return dt.replace(minute=30, second=0, microsecond=0)
        else:
            return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:  # 15 minutes
        if minutes < 8:
            return dt.replace(minute=0, second=0, microsecond=0)
        elif minutes < 23:
            return dt.replace(minute=15, second=0, microsecond=0)
        elif minutes < 38:
            return dt.replace(minute=30, second=0, microsecond=0)
        elif minutes < 53:
            return dt.replace(minute=45, second=0, microsecond=0)
        else:
            return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

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