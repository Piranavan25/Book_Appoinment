# views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Booking, Center, Service
from .serializers import BookingSerializer
from .utils import get_possible_slots, suggest_alternative_dates
from django.utils import timezone

class AvailabilityView(APIView):
    def get(self, request, center_id, date, service_id):
        center = get_object_or_404(Center, id=center_id)
        service = get_object_or_404(Service, id=service_id)
        date_obj = timezone.datetime.strptime(date, '%Y-%m-%d').date()

        slots = get_possible_slots(center, date_obj, service.duration_minutes)
        
        if not slots:
            alternatives = suggest_alternative_dates(center, service)
            return Response({
                'available': False,
                'message': 'No slots available on this date.',
                'suggested_dates': alternatives
            }, status=status.HTTP_200_OK)

        return Response({
            'available': True,
            'slots': slots[:10]  # Limit to first 10 best-fit
        })

class BookingView(APIView):
    def post(self, request):
        serializer = BookingSerializer(data=request.data)
        if serializer.is_valid():
            # Get the objects
            center = Center.objects.get(id=request.data.get('center_id'))
            service = Service.objects.get(id=request.data.get('service_id'))
            
            # Create booking with actual objects
            booking = Booking.objects.create(
                center=center,
                service=service,
                date=serializer.validated_data['date'],
                start_time=serializer.validated_data['start_time'],
                end_time=serializer.validated_data['end_time'],
                customer_name=serializer.validated_data['customer_name'],
                status=serializer.validated_data.get('status', 'booked')
            )
            return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)