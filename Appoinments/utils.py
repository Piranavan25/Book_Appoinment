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
    """Merge overlapping or adjacent intervals (with buffer)"""
    if not intervals:
        return []
    
    # Convert to list of tuples and sort
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = []
    
    current_start, current_end = sorted_intervals[0]
    
    for interval in sorted_intervals[1:]:
        start, end = interval
        
        # Check if intervals overlap or are within buffer
        if start <= current_end + timedelta(minutes=BUFFER_MINUTES):
            # Merge intervals
            current_end = max(current_end, end)
        else:
            # No overlap, add current interval to merged
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    
    # Add the last interval
    merged.append((current_start, current_end))
    
    return merged

def get_free_intervals(center, date, duration_minutes):
    """Get free intervals that can fit the duration (with buffer)"""
    workday_start_time, workday_end_time = get_workday_start_end()
    workday_start = timezone.datetime.combine(date, workday_start_time)
    workday_end = timezone.datetime.combine(date, workday_end_time)

    print(f"DEBUG: Workday - {workday_start.time()} to {workday_end.time()}")
    print(f"DEBUG: Looking for {duration_minutes} minute slots")

    # Get all bookings for the day
    bookings = Booking.objects.filter(
        center=center,
        date=date,
        status='booked'
    ).order_by('start_time')

    print(f"DEBUG: Found {bookings.count()} bookings")

    # If no bookings, the entire day is free
    if not bookings.exists():
        max_start_time = workday_end - timedelta(minutes=duration_minutes)
        if max_start_time >= workday_start:
            return [(workday_start, max_start_time)]
        else:
            return []

    # Create a timeline of busy periods (including buffers)
    busy_periods = []
    
    for booking in bookings:
        booking_start = timezone.datetime.combine(date, booking.start_time)
        booking_end = timezone.datetime.combine(date, booking.end_time)
        
        # Add buffer periods before and after each booking
        busy_start = booking_start - timedelta(minutes=BUFFER_MINUTES)
        busy_end = booking_end + timedelta(minutes=BUFFER_MINUTES)
        
        busy_periods.append((busy_start, busy_end))
        print(f"DEBUG: Busy period (with buffer): {busy_start.time()} to {busy_end.time()}")

    # Merge overlapping busy periods
    merged_busy = merge_intervals(busy_periods)
    print(f"DEBUG: Merged busy periods: {len(merged_busy)}")

    free_intervals = []
    
    # Check before first busy period
    first_busy_start = merged_busy[0][0]
    if first_busy_start > workday_start:
        free_end = first_busy_start
        free_duration = (free_end - workday_start).total_seconds() / 60
        if free_duration >= duration_minutes:
            max_start = free_end - timedelta(minutes=duration_minutes)
            free_intervals.append((workday_start, max_start))
            print(f"DEBUG: Free before first busy: {workday_start.time()} to {max_start.time()}")

    # Check between busy periods
    for i in range(len(merged_busy) - 1):
        current_busy_end = merged_busy[i][1]
        next_busy_start = merged_busy[i + 1][0]
        
        if current_busy_end < next_busy_start:
            free_start = current_busy_end
            free_end = next_busy_start
            free_duration = (free_end - free_start).total_seconds() / 60
            
            if free_duration >= duration_minutes:
                max_start = free_end - timedelta(minutes=duration_minutes)
                free_intervals.append((free_start, max_start))
                print(f"DEBUG: Free between busy: {free_start.time()} to {max_start.time()}")

    # Check after last busy period
    last_busy_end = merged_busy[-1][1]
    if last_busy_end < workday_end:
        free_start = last_busy_end
        free_end = workday_end
        free_duration = (free_end - free_start).total_seconds() / 60
        
        if free_duration >= duration_minutes:
            max_start = free_end - timedelta(minutes=duration_minutes)
            free_intervals.append((free_start, max_start))
            print(f"DEBUG: Free after last busy: {free_start.time()} to {max_start.time()}")

    print(f"DEBUG: Total free intervals found: {len(free_intervals)}")
    return free_intervals

def get_possible_slots(center, date, duration_minutes):
    """Generate possible start times in 15-min increments"""
    free_intervals = get_free_intervals(center, date, duration_minutes)
    slots = []
    
    for interval_start, interval_end in free_intervals:
        current_time = interval_start
        
        # The latest time we can start a booking in this interval
        latest_start = interval_end - timedelta(minutes=duration_minutes)
        
        print(f"DEBUG: Generating slots from {current_time.time()} to {latest_start.time()}")
        
        while current_time <= latest_start:
            end_time = current_time + timedelta(minutes=duration_minutes)
            remaining_gap = (interval_end - end_time).total_seconds() / 60
            
            slots.append({
                'start_time': current_time.time(),
                'end_time': end_time.time(),
                'gap_remaining_after': remaining_gap
            })
            
            print(f"DEBUG: Added slot {current_time.time()} to {end_time.time()}")
            
            # Move to next potential start time (15-minute increments)
            current_time += timedelta(minutes=15)
    
    print(f"DEBUG: Generated {len(slots)} total slots")
    
    # Sort by remaining gap (smallest first - best fit)
    slots.sort(key=lambda x: x['start_time'])

    return slots

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