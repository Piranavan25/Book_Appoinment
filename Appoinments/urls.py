from django.urls import path
from . import views

urlpatterns = [
    path('availability/<int:center_id>/<str:date>/<int:service_id>/', views.AvailabilityView.as_view(), name='availability'),
    path('bookings/', views.BookingView.as_view(), name='bookings'),
]