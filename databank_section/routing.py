from django.urls import path
from databank_section.consumers import NotificationConsumer,LeadNotificationConsumer

websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
    path("ws/lead-notifications/", LeadNotificationConsumer.as_asgi())
]
