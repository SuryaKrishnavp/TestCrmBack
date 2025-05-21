from celery import shared_task
from celery.exceptions import Retry
from django.core.mail import send_mail
from .models import FollowUp
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils.timezone import localtime, make_aware
from django.utils import timezone
import time
import sys
from twilio.rest import Client


TWILIO_ACCOUNT_SID = "ACe1b80056ccbacae1f088ba119ce08ccd"  # Replace with your Twilio SID
TWILIO_AUTH_TOKEN = "db0c7f6ea998625a89e9a42e0e6069c3"  # Replace with your Twilio auth token
TWILIO_WHATSAPP_FROM = "whatsapp:+919562080200"
TWILIO_CLIENT_TEMPLATE_SID = "HX5dbd4c2e3c1a9dfe658ecc1bbd586ba8"  # Replace this
TWILIO_STAFF_TEMPLATE_SID = "HX434f1543b570a22fd39556c3358519f8"  # Replace this

client_twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@shared_task(bind=True, max_retries=5, default_retry_delay=3)  # retry up to 5 times with 3 seconds delay
def send_followup_notifications(self, followup_id, notification_type):
    try:
        time.sleep(5)
        followup = FollowUp.objects.get(id=followup_id)
        followup_date = followup.followup_date

        # Ensure timezone-aware
        if timezone.is_naive(followup_date):
            followup_date = make_aware(followup_date)
        followup_date_local = localtime(followup_date)

        client_number = followup.lead.phonenumber
        staff_number = followup.follower.phonenumber
        staff_id = followup.follower.id

        # Get the names of the lead and the sales manager
        client_name = followup.lead.name  # Assuming `name` field in Leads model holds full name
        staff_name = followup.follower.username# Using first and last name of the sales manager

        # Notification content for client
        
        if notification_type == "30_min":
            # Send WhatsApp to client
            try:
                client_twilio.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:+91{client_number}",
                    content_sid=TWILIO_CLIENT_TEMPLATE_SID,
                    content_variables=f'{{"1":"{client_name}", "2":"{staff_name}", "3":"{followup_date_local.strftime("%Y-%m-%d %H:%M")}"}}'
                )
                print(f"✅ WhatsApp sent to client: {client_number}")
            except Exception as err:
                print(f"❌ Error sending to client WhatsApp: {err}")

            # Send WhatsApp to staff
            try:
                client_twilio.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:+91{staff_number}",
                    content_sid=TWILIO_STAFF_TEMPLATE_SID,
                    content_variables=f'{{"1":"{staff_name}", "2":"{client_name}", "3":"{followup_date_local.strftime("%Y-%m-%d %H:%M")}"}}'
                )
                print(f"✅ WhatsApp sent to staff: {staff_number}")
            except Exception as err:
                print(f"❌ Error sending to staff WhatsApp: {err}")

        
    except FollowUp.DoesNotExist:
        print(f"❌ Follow-up not found, retrying... (ID: {followup_id})")
        raise self.retry(exc=FollowUp.DoesNotExist(f"FollowUp {followup_id} not found"), countdown=2)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise self.retry(exc=e, countdown=5)

    finally:
        sys.stdout.flush()
