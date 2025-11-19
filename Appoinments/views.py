# views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Booking, Center, Service
from .serializers import BookingSerializer,BookingResponseSerializer
from .utils import get_possible_slots, suggest_alternative_dates
from django.utils import timezone
from rest_framework.generics import ListAPIView
from .serializers import CenterSerializer, ServiceSerializer
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


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

            # Get customer_id from request
            customer_id = request.data.get("customer_id")
            
            # 1. Fetch vehicle details from external service
            vehicle_name = request.data.get("vehicle_name")
            print("DEBUG: Received customer_id:", customer_id)
            print("DEBUG: Received vehicle_name:", vehicle_name)
            print("DEBUG: Full request data:", request.data)

            


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
                vehicle_name=vehicle_name,
                status=serializer.validated_data.get('status', 'pending')
            )
            return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class CenterListView(ListAPIView):
    queryset = Center.objects.all()
    serializer_class = CenterSerializer

class ServiceListView(ListAPIView):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer

from django.shortcuts import get_object_or_404
from .models import Booking
from .serializers import BookingSerializer
import requests
from django.http import JsonResponse

@csrf_exempt
def send_booking(request):
    try:
        # 1. Get all bookings with pending status
        pending_bookings = Booking.objects.filter(status="pending")

        if not pending_bookings.exists():
            return JsonResponse({
                "status": "empty",
                "message": "No pending bookings found"
            }, status=200)

        microservice_url = "https://httpbin.org/post"
        results = []

        # 2. Loop through each pending booking
        for booking in pending_bookings:
            serializer = BookingResponseSerializer(booking)
            data = serializer.to_dict()

            try:
                response = requests.post(
                    microservice_url,
                    json=data,
                    timeout=30
                )

                # 3. Process response
                if response.status_code in [200, 201]:
                    results.append({
                        "booking_id": booking.id,
                        "status": "pending",
                        "response": response.json()
                    })


                else:
                    results.append({
                        "booking_id": booking.id,
                        "status": "error",
                        "error_code": response.status_code,
                        "details": response.text
                    })

            except requests.exceptions.RequestException as e:
                results.append({
                    "booking_id": booking.id,
                    "status": "error",
                    "message": str(e)
                })

        # 4. Return batch results
        return JsonResponse({
            "status": "completed",
            "message": "Processed all pending bookings",
            "results": results
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": "Internal server error",
            "details": str(e)
        }, status=500)
