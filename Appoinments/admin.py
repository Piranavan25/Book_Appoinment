from django.contrib import admin
from .models import Center, Service, Booking

# Simple registration
admin.site.register(Center)
admin.site.register(Service)
admin.site.register(Booking)