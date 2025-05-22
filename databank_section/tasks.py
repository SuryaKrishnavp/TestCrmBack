from celery import shared_task
from django.core.mail import send_mail
from datetime import datetime
from .models import DataBank # Import your Lead model
from twilio.rest import Client
from django.conf import settings



TWILIO_WHATSAPP_FROM = "whatsapp:+919562080200"
TWILIO_CLIENT_TEMPLATE_SID = "HX6ad0cb700738b989ebd42340f2372c27"  # Replace this

client_twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

@shared_task
def send_followup_email(lead_id):
    lead = DataBank.objects.filter(id=lead_id).first()
    if lead:
        try:
            client_twilio.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:+91{lead.phonenumber}",
            content_sid=TWILIO_CLIENT_TEMPLATE_SID,
            content_variables=f'{{"1":"{lead.name}"}}'
            )
            print(f"✅ WhatsApp sent to client: {lead.phonenumber}")
        except Exception as err:
            print(f"❌ Error sending to client WhatsApp: {err}")
