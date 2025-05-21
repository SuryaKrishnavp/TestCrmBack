from django.shortcuts import render
from rest_framework.decorators import api_view,permission_classes
from auth_section.permissions import IsSalesManagerUser,IsCustomAdminUser
from auth_section.models import Sales_manager_reg
from rest_framework.response import Response
from .serializers import DataBankSerializer,DataBankEditSerializer,DataBankGETSerializer,DataBankImageSerializer,AdminDataBankSerializer,DataBankViewSerializer
from rest_framework import status
from .models import DataBank,DataBankImage,LeadDataFollower
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from django.db.models import Q
from django.http import JsonResponse
from .filters import DataBankFilter
from django.core.mail import send_mail
from django.conf import settings
from auth_section.models import Ground_level_managers_reg
from rest_framework.permissions import IsAuthenticated
from project_section.models import Project_db
from django.core.mail import EmailMessage
from django.conf import settings
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import os
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import pagesizes
from django.core.files.images import ImageFile
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Image
import requests
from PIL import Image as PILImage
from geopy.geocoders import Nominatim
from opencage.geocoder import OpenCageGeocode
from geopy.distance import geodesic
import re
from collections import defaultdict
from django.db.models import Count, Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils.timezone import now
from .tasks import send_followup_email
from datetime import timedelta
from datetime import datetime
from django.utils.timezone import make_aware
from twilio.rest import Client
from django.core.files.base import ContentFile
from .models import MatchingDataPdf

TWILIO_ACCOUNT_SID = "ACe1b80056ccbacae1f088ba119ce08ccd"  # Replace with your Twilio SID
TWILIO_AUTH_TOKEN = "db0c7f6ea998625a89e9a42e0e6069c3"  # Replace with your Twilio auth token
TWILIO_WHATSAPP_FROM = "whatsapp:+919562080200"
TWILIO_GLM_TEMPLATE_SID = "HX63f6fd8b9b20a9374bcb48bb6c15ca77"  # Replace this
TWILIO_MATCHEDDATA_TEMPLATE_SID = "HXeadbd83ccd838cb5a7386f8857e9d7f4" 

client_twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def Sales_lead_category_graph(request):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    sales_manager = Sales_manager_reg.objects.filter(user=staff.id).first()

    category_counts = (
        DataBank.objects
        .filter(leaddatafollower__follower=sales_manager)
        .values('lead_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return Response(category_counts)









@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def Sales_lead_category_current_month(request):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    sales_manager = Sales_manager_reg.objects.filter(user=staff.id).first()

    today = now().date()
    first_day_of_month = today.replace(day=1)

    monthly_data = (
        DataBank.objects
        .filter(timestamp__date__gte=first_day_of_month,leaddatafollower__follower=sales_manager)
        .values('lead_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return Response({
        'month': first_day_of_month.strftime('%Y-%m'),
        'data': monthly_data
    })





@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def lead_category_graph(request):
    admin_user = request.user

    if not hasattr(admin_user, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    category_counts = (
        DataBank.objects
        
        .values('lead_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return Response(category_counts)









@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def lead_category_current_month(request):
    admin_user = request.user

    if not hasattr(admin_user, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    today = now().date()
    first_day_of_month = today.replace(day=1)

    monthly_data = (
        DataBank.objects
        .filter(timestamp__date__gte=first_day_of_month)
        .values('lead_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return Response({
        'month': first_day_of_month.strftime('%Y-%m'),
        'data': monthly_data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def admin_leads_graph_data(request):
    admin = request.user
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    purposes = [
        'For Buying a Property',
        'For Selling a Property',
        'For Rental or Lease',
        'Looking to Rent or Lease Property'
    ]

    # Get only leads followed by this sales manager and for relevant purposes
    leads = DataBank.objects.filter(
        purpose__in=purposes
    )

    # Aggregate grouped counts in one DB query
    aggregated = (
        leads
        .values('purpose')
        .annotate(
            total_leads=Count('id'),
            closed_successfully_leads=Count('id', filter=Q(stage="Closed Successfully")),
            unsuccessfully_closed_leads=Count('id', filter=Q(stage__in=["Closed by Someone", "Dropped Lead"])),
            pending_leads=Count('id', filter=Q(stage="Pending"))  # Assuming "Pending" = new lead
        )
    )

    # Convert to dict for fast lookup
    data_by_purpose = {item['purpose']: item for item in aggregated}

    # Build final response ensuring all 4 purposes are present
    graph_data = []
    for purpose in purposes:
        item = data_by_purpose.get(purpose, {})
        graph_data.append({
            "purpose": purpose,
            "total_leads": item.get('total_leads', 0),
            "closed_successfully_leads": item.get('closed_successfully_leads', 0),
            "unsuccessfully_closed_leads": item.get('unsuccessfully_closed_leads', 0),
            "pending_leads":item.get(' pending_leads',0)
        })

    return Response({"graph_data": graph_data}, status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def get_successfullyclosed_leads(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    # Get leads with status = "Not Opened" and order by timestamp (newest first)
    leads = DataBank.objects.filter(stage="Closed Successfully").order_by('-timestamp')
    
    # Serialize leads data
    serializer = DataBankViewSerializer(leads, many=True)
    
    return Response(serializer.data, status=200)


from django.db.models import Q

@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def get_unsuccessfullyclosed_leads(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    # Get leads with status = "Not Opened" and order by timestamp (newest first)
    leads = DataBank.objects.filter(
        Q(stage="Closed by Someone") | Q(stage="Droped Lead")
    ).order_by('-timestamp')    
    # Serialize leads data
    serializer = DataBankViewSerializer(leads, many=True)
    
    return Response(serializer.data, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def get_pending_leads(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    # Get leads with status = "Not Opened" and order by timestamp (newest first)
    leads = DataBank.objects.filter(
        Q(stage="Pending") 
    ).order_by('-timestamp')    
    # Serialize leads data
    serializer = DataBankViewSerializer(leads, many=True)
    
    return Response(serializer.data, status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def followed_leads_admin(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    
    followed_leads = DataBank.objects.filter(status="Followed").order_by('-timestamp')
    serializer = DataBankViewSerializer(followed_leads,many=True).data
    return Response(serializer,status=200)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def add_lead_by_admin(request):
    admin = request.user
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data.copy()
    follower_id = data.pop("follower_id", None)

    lead_serializer = AdminDataBankSerializer(data=data)  # You'll need to create/use a serializer for DataBank

    if lead_serializer.is_valid():
        
        lead = lead_serializer.save()
        if follower_id:
            try:
                follower = Sales_manager_reg.objects.get(id=follower_id)
                LeadDataFollower.objects.create(lead=lead, follower=follower)
                lead.status = "Followed"
                lead.save()
            except Sales_manager_reg.DoesNotExist:
                return Response({'error': 'Invalid follower_id'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Lead added successfully'}, status=status.HTTP_201_CREATED)
    else:
        return Response(lead_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def add_follower(request,data_id):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    
    lead = DataBank.objects.filter(id=data_id).first()  
    
    if not lead:
        return Response({"error": "Lead not found"}, status=404)
    sales_manager_id = request.data.get('sales_manager_id')
    if not sales_manager_id:
        return Response({"error": "Sales Manager ID is required"}, status=400)

    sales_manager = Sales_manager_reg.objects.filter(id=sales_manager_id).first()
    if not sales_manager:
        return Response({"error": "Sales Manager not found"}, status=404)
    LeadDataFollower.objects.create(
        lead = lead,
        follower = sales_manager
    )
    lead.status = "Followed"
    lead.save()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "lead_notifications",
        {
            "type": "send_notification",
            "message": {
                "follower":sales_manager.username,
                "lead_id": lead.id,
                "message": f"{sales_manager.username} followed Lead id:({lead.id}) successfully"
            }
        }  
    )
    send_follower_email(sales_manager, lead)
    return Response({'message': "Successfully add follower to the lead"}, status=200)

def send_follower_email(sales_manager, lead):
    subject = f"New Lead Assigned: {lead.id}"
    message = f"""
    Dear {sales_manager.username},

    You have been added as a follower to Lead ID: {lead.id}.
    
    Lead Details:
    - Lead Name: {lead.name}
    - Lead Status: {lead.status}

    Please log in to your account to manage and follow up with the lead.

    Regards,
    DEVLOK CRM Team
    """
    
    from_email = 'devlokpromotions@gmail.com'
    recipient_list = [sales_manager.email]  # Send to sales manager's email
    
    # Send email
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def Admin_graph_Leads(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    total_leads = DataBank.objects.all().count()
    successfully_closed = DataBank.objects.filter(stage="Closed Successfully").count()
    unsuccess_leads = DataBank.objects.filter(stage__in=["Closed by Someone", "Droped Lead"]).count()
    followed_leads=DataBank.objects.filter(status="Followed").count()
    
    return Response({
        "total_leads": total_leads,
        "followed_leads": followed_leads,
        "successfully_closed": successfully_closed,
        "unsuccess_leads": unsuccess_leads,
        
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def Admin_crm_performance_graph(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    

    leads = DataBank.objects.all()

    monthly_data = defaultdict(lambda: {"total": 0, "closed": 0})

    for lead in leads:
        if not lead.timestamp:
            continue

        month_key = lead.timestamp.strftime('%Y-%m')
        monthly_data[month_key]["total"] += 1

        if lead.stage == 'Closed Successfully' and lead.closed_date:
            monthly_data[month_key]["closed"] += 1

    result = []
    for month, data in sorted(monthly_data.items()):
        total = data["total"]
        closed = data["closed"]
        conversion_rate = round((closed / total) * 100, 2) if total else 0.0

        result.append({
            "month": month,
            "total_leads": total,
            "closed_success": closed,
            "conversion_rate": conversion_rate
        })

    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])  # Ensure the user is authenticated and a Sales Manager
def SM_monthly_performance(request):
    # The user is automatically set via JWT
    salesmanager = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(salesmanager, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)

    staff = Sales_manager_reg.objects.filter(user=salesmanager.id).first()
    
    # Calculate the start of the current month
    today = now().date()
    start_of_month = today.replace(day=1)  # First day of current month
    start_of_month_datetime = make_aware(datetime.combine(start_of_month, datetime.min.time()))

    # Get total leads for this Sales Manager created this month
    total_leads = DataBank.objects.filter(
        leaddatafollower__follower=staff,
        timestamp__gte=start_of_month_datetime
    ).count()

    # Get successfully closed leads in this month
    closed_successfully = DataBank.objects.filter(
        leaddatafollower__follower=staff,
        stage="Closed Successfully",
        closed_date__isnull=False,  # Only leads that have a closed date
        closed_date__gte=start_of_month
    ).count()

    # Calculate percentage of leads closed successfully
    success_percentage = (
        (closed_successfully / total_leads) * 100 if total_leads > 0 else 0
    )

    # Prepare the response data for graph plotting
    response_data = {
        "total_leads": total_leads,
        "closed_successfully": closed_successfully,
        "success_percentage": round(success_percentage, 2),
    }

    return Response(response_data, status=200)




@api_view(['POST'])
@permission_classes([])  # Or use IsAuthenticated if needed
def import_databank_entry(request):
    try:
        data = request.data
        DataBank.objects.create(
            name=data.get('name'),
            phonenumber=data.get('phonenumber'),
            district=data.get('district'),
            place=data.get('place'),
            location_preferences=data.get('location_preferences'),
            address=data.get('address'),
            purpose=data.get('purpose'),
            mode_of_property=data.get('mode_of_property'),
            demand_price=data.get('demand_price') or None,
            advance_price=data.get('advance_price') or None,
            area_in_sqft=data.get('area_in_sqft'),
            area_in_cent=data.get('area_in_cent'),
            building_roof=data.get('building_roof'),
            number_of_floors=data.get('number_of_floors'),
            building_bhk=data.get('building_bhk'),
            additional_note=data.get('additional_note'),
            location_link=data.get('location_link'),
            lead_category=data.get('lead_category'),
            image_folder=data.get('image_folder'),
            status=data.get('status', 'Pending'),
            stage=data.get('stage', 'Pending'),
            closed_date=data.get('closed_date') or None,
            care_of=data.get('care_of')
        )
        return Response({"message": "Entry created"}, status=201)
    except Exception as e:
        return Response({"error": str(e)}, status=400)







@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_new_data(request):
    
    new_leads = DataBank.objects.filter(
        status="Pending"
    ).order_by('-timestamp')

    serializer = DataBankSerializer(new_leads, many=True)
    return Response(serializer.data, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def Follow_lead_data(request,lead_id):
    SManager = request.user
    sales_manager = Sales_manager_reg.objects.filter(user=SManager.id).first()
    lead = DataBank.objects.filter(id=lead_id).first()  
    
    if not lead:
        return Response({"error": "Lead not found"}, status=404)

    LeadDataFollower.objects.create(
        lead = lead,
        follower = sales_manager
    )
    lead.status = "Followed"
    lead.save()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "lead_notifications",
        {
            "type": "send_notification",
            "message": {
                "follower":sales_manager.username,
                "lead_id": lead.id,
                "message": f"{sales_manager.username}  followed the Lead({lead.id}) successfully"
            }
        }  
    )
    return Response({'message': "Successfully followed the lead"}, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def manually_enter_data(request):
    staff = request.user
    salesmanager = Sales_manager_reg.objects.filter(user=staff).first()
    if not salesmanager:
        return Response({'message': 'Unauthorized user'}, status=403)

    serializer = DataBankSerializer(data=request.data)
    if serializer.is_valid():
        lead = serializer.save()
        lead.status = "Followed"
        lead.save()

        # Add the sales manager as the follower
        LeadDataFollower.objects.create(
            lead=lead,
            follower=salesmanager
        )

        return Response({'message': 'Lead added successfully'}, status=201)

    return Response(serializer.errors, status=400)







@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def get_followeddata_salesmanager(request):
    staff = request.user

    # Ensure the user is a sales manager
    salesmanager = getattr(staff, 'sales_manager_reg', None)
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=403)

    # Get all followed leads for this sales manager
    followed_leads = DataBank.objects.filter(
        leaddatafollower__follower=salesmanager,
        status="Followed"
    ).order_by('-timestamp')

    serializer = DataBankSerializer(followed_leads, many=True)
    return Response(serializer.data, status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def successfully_closed_data_salesmanager(request):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    successfully_closed_leads = DataBank.objects.filter( leaddatafollower__follower=salesmanager,stage="Closed Successfully").order_by('-timestamp')
    serializer = DataBankSerializer(successfully_closed_leads,many=True).data
    return Response(serializer,status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def unsuccessfully_closed_data_salesmanager(request):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    
    leads = DataBank.objects.filter(
        leaddatafollower__follower=salesmanager,  # ✅ Filter by staff_id only
        stage__in=["Closed by Someone", "Droped Lead"]  # ✅ Stage condition
    ).order_by('-timestamp')
    serializer = DataBankSerializer(leads,many=True).data
    return Response(serializer,status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def pending_data_salesmanager(request):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    
    leads = DataBank.objects.filter(
        leaddatafollower__follower=salesmanager,
        stage__in=["Not Opened", "Pending"]  
    ).order_by('-timestamp')
    serializer = DataBankSerializer(leads,many=True).data
    return Response(serializer,status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def salesmanager_crm_performance_con(request):
    staff = request.user

    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Sales Manager not found"}, status=status.HTTP_404_NOT_FOUND)

    leads = DataBank.objects.filter(leaddatafollower__follower=salesmanager)

    monthly_data = defaultdict(lambda: {"total": 0, "closed": 0})

    for lead in leads:
        if not lead.timestamp:
            continue

        month_key = lead.timestamp.strftime('%Y-%m')
        monthly_data[month_key]["total"] += 1

        if lead.stage == 'Closed Successfully' and lead.closed_date:
            monthly_data[month_key]["closed"] += 1

    result = []
    for month, data in sorted(monthly_data.items()):
        total = data["total"]
        closed = data["closed"]
        conversion_rate = round((closed / total) * 100, 2) if total else 0.0

        result.append({
            "month": month,
            "total_leads": total,
            "closed_success": closed,
            "conversion_rate": conversion_rate
        })

    return Response(result, status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def get_detailed_data_salesmanager(request,data_id):
    staff = request.user

    # Ensure the user is a sales manager
    salesmanager = getattr(staff, 'sales_manager_reg', None)
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=403)

    # Get all followed leads for this sales manager
    try:
        followed_leads = DataBank.objects.get(
            leaddatafollower__follower=salesmanager,
            status="Followed",
            id=data_id
        )
    except DataBank.DoesNotExist:
        return Response({"error": "DataBank entry not found or not followed by you."}, status=404)


    serializer = DataBankSerializer(followed_leads)
    return Response(serializer.data, status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def salesmanager_crm_graph_data(request):
    staff = request.user

    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    total_leads = DataBank.objects.filter(leaddatafollower__follower=salesmanager).count()
    successfully_closed = DataBank.objects.filter(leaddatafollower__follower=salesmanager,stage="Closed Successfully").count()
    unsuccess_leads = DataBank.objects.filter(leaddatafollower__follower=salesmanager,
                                           stage__in=["Closed by Someone", "Dropped Lead"]).count()
    followed_leads=DataBank.objects.filter(leaddatafollower__follower=salesmanager,status="Followed").count()
    
    return Response({
        "total_leads": total_leads,
        "followed_leads": followed_leads,
        "successfully_closed": successfully_closed,
        "unsuccess_leads": unsuccess_leads,
        
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def salesmanager_purpose_piechart_data(request):
    user = request.user

    if not hasattr(user, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    salesmanager = user.sales_manager_reg

    purposes = [
        'For Buying a Property',
        'For Selling a Property',
        'For Rental or Lease',
        'Looking to Rent or Lease Property'
    ]

    # Get only leads followed by this sales manager and for relevant purposes
    leads = DataBank.objects.filter(
        leaddatafollower__follower=salesmanager,
        purpose__in=purposes
    )

    # Aggregate grouped counts in one DB query
    aggregated = (
        leads
        .values('purpose')
        .annotate(
            total_leads=Count('id'),
            closed_successfully_leads=Count('id', filter=Q(stage="Closed Successfully")),
            unsuccessfully_closed_leads=Count('id', filter=Q(stage__in=["Closed by Someone", "Dropped Lead"])),
            pending_leads=Count('id', filter=Q(stage="Pending"))  # Assuming "Pending" = new lead
        )
    )

    # Convert to dict for fast lookup
    data_by_purpose = {item['purpose']: item for item in aggregated}

    # Build final response ensuring all 4 purposes are present
    graph_data = []
    for purpose in purposes:
        item = data_by_purpose.get(purpose, {})
        graph_data.append({
            "purpose": purpose,
            "total_leads": item.get('total_leads', 0),
            "closed_successfully_leads": item.get('closed_successfully_leads', 0),
            "unsuccessfully_closed_leads": item.get('unsuccessfully_closed_leads', 0),
            "pending_leads":item.get(' pending_leads',0)
        })

    return Response({"graph_data": graph_data}, status=status.HTTP_200_OK)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def store_data_into_db(request):
    user = request.user
    sales_manager = Sales_manager_reg.objects.filter(user=user.id).first()

    if not sales_manager:
        return Response({"error": "Sales Manager not found"}, status=status.HTTP_404_NOT_FOUND)


    serializer = DataBankSerializer(data=request.data)

    if serializer.is_valid():
        validated_data = serializer.validated_data
        databank_entry = DataBank.objects.create(
            timestamp=timezone.now(),
            **validated_data
        )

        # Create a LeadDataFollower entry
        LeadDataFollower.objects.create(
            lead=databank_entry,
            follower=sales_manager
        )
        
        return Response({"success": "Data stored successfully", "id": databank_entry.id}, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def update_databank(request, databank_id):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)

    sales_manager = staff.sales_manager_reg

    # Try to fetch the DataBank entry
    try:
        databank = DataBank.objects.get(id=databank_id)
    except DataBank.DoesNotExist:
        return Response({"error": "DataBank entry not found"}, status=404)

    # Check if the current Sales Manager is the follower of this DataBank entry
    is_follower = LeadDataFollower.objects.filter(lead=databank, follower=sales_manager).exists()
    if not is_follower:
        return Response({"error": "You are not authorized to update this entry."}, status=403)

    # Proceed with partial update
    serializer = DataBankEditSerializer(databank, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()

        
        return Response(serializer.data, status=200)

    return Response(serializer.errors, status=400)




@api_view(['PUT'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def Update_data_stage(request,data_id):
    staff = request.user

    # Ensure the authenticated user is a Sales Manager
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    sales_manager = Sales_manager_reg.objects.filter(user=staff.id).first()
    lead = DataBank.objects.filter(id=data_id,leaddatafollower__follower=sales_manager).first()  
    
    if not lead:
        return Response({"error": "Lead not found"}, status=404)

    updated_stage = request.data.get("stage")
    

    if updated_stage in ["Closed by Someone", "Droped Lead"]:
        send_followup_email.apply_async((lead.id,), eta=now() + timedelta(days=365))
    lead.stage = updated_stage
    lead.closed_date = now().date()
    lead.save()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "lead_notifications",
        {
            "type": "send_notification",
            "message": {
                "follower":sales_manager.username,
                "lead_id": lead.id,
                "new_stage": updated_stage,
                "message": "Lead stage updated successfully"
            }
        }
    )
    
    return Response({'message': "Successfully updated stage"}, status=200)




@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def autocomplete_databank(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({"suggestions": []})

    matches = DataBank.objects.filter(
        Q(name__icontains=query) |
        Q(district__icontains=query) |
        Q(place__icontains=query)
    ).values_list('name', 'district', 'place')

    suggestions = set()
    for name, district, place in matches:
        if name and query.lower() in name.lower():
            suggestions.add(name)
        if district and query.lower() in district.lower():
            suggestions.add(district)
        if place and query.lower() in place.lower():
            suggestions.add(place)

    return JsonResponse({"suggestions": list(suggestions)})



@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def databank_suggestions(request):
    query = request.GET.get("q", "").strip()
    suggestions = set()

    if not query:
        return Response({"suggestions": []})

    matching_items = DataBank.objects.filter(
        Q(name__icontains=query) |
        Q(district__icontains=query) |
        Q(place__icontains=query)
    ).values_list("name", "district", "place")

    for name, district, place in matching_items:
        if name and query.lower() in name.lower():
            suggestions.add(name)
        if district and query.lower() in district.lower():
            suggestions.add(district)
        if place and query.lower() in place.lower():
            suggestions.add(place)

    return Response({"suggestions": list(suggestions)[:10]})  # limit to top 10


from project_section.serializers import ProjectSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def search_databank(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({"error": "Query parameter is required"}, status=400)

    # 1️⃣ Search in Databank
    databank_results = DataBank.objects.filter(
        Q(name__icontains=query) |
        Q(email__icontains=query) |
        Q(phonenumber__icontains=query) |
        Q(district__icontains=query) |
        Q(place__icontains=query) |
        Q(purpose__icontains=query) |
        Q(mode_of_property__icontains=query) |
        Q(demand_price__icontains=query) |
        Q(location_proposal_district__icontains=query) |
        Q(location_proposal_place__icontains=query) |
        Q(area_in_sqft__icontains=query) |
        Q(building_roof__icontains=query) |
        Q(number_of_floors__icontains=query) |
        Q(building_bhk__icontains=query) |
        Q(projects__project_name__icontains=query) |
        Q(projects__importance__icontains=query)
    )

    if databank_results.exists():
        return JsonResponse({
            "source": "databank",
            "results": DataBankGETSerializer(databank_results, many=True).data
        })

    # 2️⃣ If no Databank results, search in Leads
    lead_results = Leads.objects.filter(
        Q(name__icontains=query) |
        Q(email__icontains=query) |
        Q(phonenumber__icontains=query) |
        Q(district__icontains=query) |
        Q(place__icontains=query) |
        Q(purpose__icontains=query) |
        Q(mode_of_purpose__icontains=query) |
        Q(message__icontains=query) |
        Q(status__icontains=query) |
        Q(stage__icontains=query) |
        Q(follower__icontains=query)
    )

    if lead_results.exists():
        return JsonResponse({
            "source": "leads",
            "results": LeadsViewSerializer(lead_results, many=True).data
        })

    # 3️⃣ If no Leads results, search in Projects
    project_results = Project_db.objects.filter(
        Q(project_name__icontains=query) |
        Q(importance__icontains=query) |
        Q(description__icontains=query)
    )

    if project_results.exists():
        return JsonResponse({
            "source": "projects",
            "results": ProjectSerializer(project_results, many=True).data
        })

    # 4️⃣ If no matches found in any, return empty response
    return JsonResponse({"source": "none", "results": []})








@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def autocomplete_databank_salesmanager(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({"suggestions": []})

    staff = request.user
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return JsonResponse({"error": "Not a valid sales manager"}, status=403)

    # Filter DataBank records where any field contains the query string (name, district, place)
    matches = DataBank.objects.filter(
        Q(name__icontains=query) | 
        Q(district__icontains=query) | 
        Q(place__icontains=query),
        leaddatafollower__follower=salesmanager
    ).values_list('name', 'district', 'place')

    suggestions = set()

    for name, district, place in matches:
        # Add only the parts that contain the query string
        if name and query.lower() in name.lower():
            suggestions.add(name)
        if district and query.lower() in district.lower():
            suggestions.add(district)
        if place and query.lower() in place.lower():
            suggestions.add(place)

    return JsonResponse({"suggestions": list(suggestions)})





@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSalesManagerUser])
def salesmanager_search_databank(request):
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({"error": "Query parameter is required"}, status=400)

    staff = request.user

    # Check if the user is a sales manager
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    # 1️⃣ Search in Databank (only valid fields)
    databank_results = DataBank.objects.filter(
        (Q(name__icontains=query) |
         Q(phonenumber__icontains=query) |
         Q(district__icontains=query) |
         Q(place__icontains=query) |
         Q(purpose__icontains=query) |
         Q(mode_of_property__icontains=query) |
         Q(demand_price__icontains=query) |
         Q(location_preferences__icontains=query) |
         Q(area_in_sqft__icontains=query) |
         Q(building_roof__icontains=query) |
         Q(number_of_floors__icontains=query) |
         Q(building_bhk__icontains=query) |
         Q(projects__project_name__icontains=query) |
         Q(projects__importance__icontains=query)),
        leaddatafollower__follower=salesmanager
    )

    if databank_results.exists():
        return JsonResponse({
            "source": "databank",
            "results": DataBankGETSerializer(databank_results, many=True).data
        })

    # 3️⃣ If no Leads results, search in Projects
    project_results = Project_db.objects.filter(
        (Q(project_name__icontains=query) |
         Q(importance__icontains=query) |
         Q(description__icontains=query)) &
        Q(data_bank__follower=salesmanager)
    )

    if project_results.exists():
        return JsonResponse({
            "source": "projects",
            "results": ProjectSerializer(project_results, many=True).data
        })

    # 4️⃣ If no matches found in any, return empty response
    return JsonResponse({"source": "none", "results": []})









OPENCAGE_API_KEY = 'c445fce3f1b14cba8c08daafb182d5f3'  # Replace with your actual API key
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# Geocode place name to (lat, lng)
def geocode_location(place_name):
    try:
        query = f"{place_name}, Kerala, India"
        results = geocoder.geocode(query)
        if results:
            lat = results[0]['geometry']['lat']
            lng = results[0]['geometry']['lng']
            return (lat, lng)
    except Exception as e:
        print(f"Geocoding error for '{place_name}': {e}")
    return None

# Extract coordinates from comma-separated string (e.g., "10.123,76.456")
def extract_coordinates(link):
    if not link:
        return None
    try:
        lat, lon = map(float, link.split(','))
        return (lat, lon)
    except ValueError as e:
        print(f"Invalid coordinates in link '{link}': {e}")
        return None

# Main API view for filtering DataBank entries
@api_view(['GET'])
@permission_classes([AllowAny])
def filter_data_banks(request):
    queryset = DataBank.objects.all()
    filters = DataBankFilter(request.GET, queryset=queryset).qs

    district = request.GET.get('district')
    place = request.GET.get('place')  # corrected param key to 'place'
    distance_km = request.GET.get('distance_km')

    # Geolocation distance filtering if applicable
    if distance_km and (place or district):
        try:
            distance_km = float(distance_km)
            base_coords = geocode_location(place) if place else None
            if not base_coords and district:
                base_coords = geocode_location(district)

            if not base_coords:
                return Response({"error": "Could not geocode the provided place or district."},
                                status=status.HTTP_400_BAD_REQUEST)

            filtered_ids = []
            for obj in filters:
                coords = extract_coordinates(obj.location_link)
                if coords:
                    try:
                        dist = geodesic(base_coords, coords).km
                        if dist <= distance_km:
                            filtered_ids.append(obj.id)
                    except Exception as e:
                        print(f"Distance calc error for ID {obj.id}: {e}")

            filters = filters.filter(id__in=filtered_ids)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    serializer = DataBankViewSerializer(filters, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)



from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time


geolocator = Nominatim(user_agent="devlok-matcher")

def get_coordinates(place_name, retries=3, delay=1):
    if not place_name:
        return None
    for _ in range(retries):
        try:
            location = geolocator.geocode(f"{place_name}, Kerala, India", timeout=10)
            if location:
                return (location.latitude, location.longitude)
        except GeocoderTimedOut:
            time.sleep(delay)
        except Exception as e:
            print(f"Geopy error for '{place_name}': {e}")
            break
    return None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_matching_pdf(request, property_id):
    def normalize_area(value):
        try:
            if value:
                return float(re.sub(r"[^\d.]", "", value))  # Clean up input
        except:
            return None
        return None

    try:
        new_property = get_object_or_404(DataBank, id=property_id)

        opposite_purpose_map = {
            "For Selling a Property": "For Buying a Property",
            "For Buying a Property": "For Selling a Property",
            "For Rental or Lease": "Looking to Rent or Lease Property",
            "Looking to Rent or Lease Property": "For Rental or Lease",
        }
        opposite_purpose = opposite_purpose_map.get(new_property.purpose)

        potential_matches = DataBank.objects.filter(
            purpose=opposite_purpose,
            mode_of_property=new_property.mode_of_property,
        )

        if not potential_matches.exists():
            potential_matches = DataBank.objects.filter(
                purpose=opposite_purpose,
                mode_of_property__in=["other", new_property.mode_of_property],
            )

        # Get coordinates for distance calculation
        if new_property.purpose in ["For Buying a Property", "Looking to Rent or Lease Property"]:
            location_pref = new_property.location_preferences or ""
            new_coords = get_coordinates(location_pref)
        else:
            new_coords = get_coordinates(new_property.place)

        ranked_matches = []
        for match in potential_matches:
            score = 0

            if match.mode_of_property == new_property.mode_of_property:
                score += 4

            # ✅ Strict Location Match Check
            location_match = False

            if new_property.purpose in ["For Buying a Property", "Looking to Rent or Lease Property"]:
                if new_property.location_preferences:
                    if match.district and match.district.lower() in new_property.location_preferences.lower():
                        location_match = True
                    elif match.place and match.place.lower() in new_property.location_preferences.lower():
                        location_match = True
                match_coords = get_coordinates(match.place)

            else:
                if match.location_preferences:
                    if new_property.district and new_property.district.lower() in match.location_preferences.lower():
                        location_match = True
                    elif new_property.place and new_property.place.lower() in match.location_preferences.lower():
                        location_match = True
                match_coords = get_coordinates(match.location_preferences)

            if not location_match:
                continue  # ❌ Skip match if no location alignment

            score += 5  # ✅ Reward for location match

            # 🌍 Geo distance score
            if new_coords and match_coords:
                try:
                    distance_km = geodesic(new_coords, match_coords).km
                    if distance_km <= 5:
                        score += 5
                    elif distance_km <= 10:
                        score += 3
                    elif distance_km <= 20:
                        score += 1
                except:
                    pass

            # 💰 Demand Price Match
            try:
                if match.demand_price is not None and new_property.demand_price is not None:
                    if float(match.demand_price) * 0.9 <= float(new_property.demand_price) <= float(match.demand_price) * 1.1:
                        score += 5
            except:
                pass

            # 📐 Enhanced Area Matching (sqft & cent)
            match_sqft = normalize_area(match.area_in_sqft)
            new_sqft = normalize_area(new_property.area_in_sqft)
            match_cent = normalize_area(match.area_in_cent)
            new_cent = normalize_area(new_property.area_in_cent)

            if match_sqft and new_sqft and match_sqft * 0.9 <= new_sqft <= match_sqft * 1.1:
                score += 2
            elif match_sqft or new_sqft:
                score += 1  # Partial area info

            if match_cent and new_cent and match_cent * 0.9 <= new_cent <= match_cent * 1.1:
                score += 2
            elif match_cent or new_cent:
                score += 1

            # 🏠 House features
            if match.building_bhk and new_property.building_bhk and match.building_bhk == new_property.building_bhk:
                score += 2
            if match.number_of_floors and new_property.number_of_floors and match.number_of_floors == new_property.number_of_floors:
                score += 1
            if match.building_roof and new_property.building_roof and match.building_roof == new_property.building_roof:
                score += 1

            if score > 0:
                ranked_matches.append((score, match))

        # Sort by score descending
        ranked_matches.sort(reverse=True, key=lambda x: x[0])

        

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50, leftMargin=40, rightMargin=40)
        styles = getSampleStyleSheet()
        content = []

        # --- Header with Logo and Background ---
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'devicon.jpg')  # <-- Update this to the correct path of your logo
        logo = RLImage(logo_path, width=80, height=80)  # Resize as needed

        header_main_style = ParagraphStyle(
            name='HeaderMain',
            fontSize=16,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        header_sub_style = ParagraphStyle(
            name='HeaderSub',
            fontSize=8,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        header_data = [[
            logo,
            Paragraph("<b>DEVELOK DEVELOPERS</b><br/>Thrissur, Kerala<br/> 9846845777 | 9645129777<br/> info@devlokdevelopers.com |  www.devlokdevelopers.com", header_sub_style)
        ]]

        header_table = Table(header_data, colWidths=[60, 450])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#0564BC")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        content.append(header_table)
        content.append(Spacer(1, 12))

        # Custom styles for the content
        normal_style = ParagraphStyle(name='Normal', fontSize=10, leading=14)
        footer_style = ParagraphStyle(name='Footer', fontSize=8, textColor=colors.grey, alignment=TA_CENTER)

        # Intro text
        intro = (
            "We are excited to present a curated list of properties that closely match your preferences. "
            "Here are our top picks based on your recent property entry:"
        )
        content.append(Paragraph(intro, normal_style))
        content.append(Spacer(1, 20))

        # Matching Properties section
        for score, prop in ranked_matches[:5]:
            details = f"""
            <b>District:</b> {prop.district} &nbsp;&nbsp; <b>Place:</b> {prop.place}<br/>
            <b>Purpose:</b> {prop.purpose} &nbsp;&nbsp; <b>Type:</b> {prop.mode_of_property}<br/>
            <b>Price:</b> {prop.demand_price} &nbsp;&nbsp; <b>Area:</b> {prop.area_in_sqft} sqft<br/>
            <b>BHK:</b> {prop.building_bhk or 'N/A'} &nbsp;&nbsp; <b>Floors:</b> {prop.number_of_floors or 'N/A'}<br/>
            <b>Roof Type:</b> {prop.building_roof or 'N/A'}<br/>
            <b>Additional Notes:</b> {prop.additional_note or 'None'}
            """
            content.append(Paragraph(details, normal_style))
            content.append(Spacer(1, 6))
            content.append(Spacer(1, 12))
            content.append(Table([[" " * 150]], style=[("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.grey)]))
            content.append(Spacer(1, 12))

        content.append(Spacer(1, 10))
        content.append(Paragraph("Generated by <b>DEVELOK DEVELOPERS Matching Engine</b>", footer_style))

        # Watermark function
        def add_watermark(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.2)
            canvas.translate(300, 400)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "DEVELOK DEVELOPERS")
            canvas.restoreState()

        # Build the document with watermark on every page
        doc.build(content, onFirstPage=add_watermark, onLaterPages=add_watermark)

        buffer.seek(0)
        pdf_filename = f"matching_properties_{property_id}.pdf"
        pdf_bytes = buffer.getvalue()  # This contains the full PDF content

        # Create instance and attach PDF to it
        pdf_record = MatchingDataPdf()
        pdf_record.matching_pdf.save(pdf_filename, ContentFile(pdf_bytes))
        pdf_record.save()
        phonenumber = new_property.phonenumber
        
        try:
            client_twilio.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:+91{phonenumber}",
            content_sid=TWILIO_MATCHEDDATA_TEMPLATE_SID,
            content_variables=f'{{"1":"{pdf_filename}"}}'
            )
            print(f"✅ WhatsApp sent to client: {phonenumber}")
            pdf_record.delete()
            return Response({
                "message": "PDF saved and sent successfully.",
            })
        except Exception as err:
            print(f"❌ Error sending to client WhatsApp: {err}")

        
        

    except Exception as e:
        return Response({"error": str(e)}, status=500)










import re

@api_view(['GET'])
@permission_classes([AllowAny])
def match_property(request, property_id):
    def normalize_area(value):
        try:
            if value:
                return float(re.sub(r"[^\d.]", "", value))  # Clean up input
        except:
            return None
        return None

    try:
        new_property = get_object_or_404(DataBank, id=property_id)

        opposite_purpose_map = {
            "For Selling a Property": "For Buying a Property",
            "For Buying a Property": "For Selling a Property",
            "For Rental or Lease": "Looking to Rent or Lease Property",
            "Looking to Rent or Lease Property": "For Rental or Lease",
        }
        opposite_purpose = opposite_purpose_map.get(new_property.purpose)

        potential_matches = DataBank.objects.filter(
            purpose=opposite_purpose,
            mode_of_property=new_property.mode_of_property,
        )

        if not potential_matches.exists():
            potential_matches = DataBank.objects.filter(
                purpose=opposite_purpose,
                mode_of_property__in=["other", new_property.mode_of_property],
            )

        # Get coordinates for distance calculation
        if new_property.purpose in ["For Buying a Property", "Looking to Rent or Lease Property"]:
            location_pref = new_property.location_preferences or ""
            new_coords = get_coordinates(location_pref)
        else:
            new_coords = get_coordinates(new_property.place)

        ranked_matches = []
        for match in potential_matches:
            score = 0

            if match.mode_of_property == new_property.mode_of_property:
                score += 4

            # ✅ Strict Location Match Check
            location_match = False

            if new_property.purpose in ["For Buying a Property", "Looking to Rent or Lease Property"]:
                if new_property.location_preferences:
                    if match.district and match.district.lower() in new_property.location_preferences.lower():
                        location_match = True
                    elif match.place and match.place.lower() in new_property.location_preferences.lower():
                        location_match = True
                match_coords = get_coordinates(match.place)

            else:
                if match.location_preferences:
                    if new_property.district and new_property.district.lower() in match.location_preferences.lower():
                        location_match = True
                    elif new_property.place and new_property.place.lower() in match.location_preferences.lower():
                        location_match = True
                match_coords = get_coordinates(match.location_preferences)

            if not location_match:
                continue  # ❌ Skip match if no location alignment

            score += 5  # ✅ Reward for location match

            # 🌍 Geo distance score
            if new_coords and match_coords:
                try:
                    distance_km = geodesic(new_coords, match_coords).km
                    if distance_km <= 5:
                        score += 5
                    elif distance_km <= 10:
                        score += 3
                    elif distance_km <= 20:
                        score += 1
                except:
                    pass

            # 💰 Demand Price Match
            try:
                if match.demand_price is not None and new_property.demand_price is not None:
                    if float(match.demand_price) * 0.9 <= float(new_property.demand_price) <= float(match.demand_price) * 1.1:
                        score += 5
            except:
                pass

            # 📐 Enhanced Area Matching (sqft & cent)
            match_sqft = normalize_area(match.area_in_sqft)
            new_sqft = normalize_area(new_property.area_in_sqft)
            match_cent = normalize_area(match.area_in_cent)
            new_cent = normalize_area(new_property.area_in_cent)

            if match_sqft and new_sqft and match_sqft * 0.9 <= new_sqft <= match_sqft * 1.1:
                score += 2
            elif match_sqft or new_sqft:
                score += 1  # Partial area info

            if match_cent and new_cent and match_cent * 0.9 <= new_cent <= match_cent * 1.1:
                score += 2
            elif match_cent or new_cent:
                score += 1

            # 🏠 House features
            if match.building_bhk and new_property.building_bhk and match.building_bhk == new_property.building_bhk:
                score += 2
            if match.number_of_floors and new_property.number_of_floors and match.number_of_floors == new_property.number_of_floors:
                score += 1
            if match.building_roof and new_property.building_roof and match.building_roof == new_property.building_roof:
                score += 1

            if score > 0:
                ranked_matches.append((score, match))

        # Sort by score descending
        ranked_matches.sort(reverse=True, key=lambda x: x[0])

        if ranked_matches:
            serialized_matches = [
                {"score": score, "data": DataBankGETSerializer(match).data}
                for score, match in ranked_matches
            ]
            return Response(
                {"total_matches": len(ranked_matches), "matches": serialized_matches},
                status=200
            )

        # No matches: Notify ground staff
        ground_staff_phonenumbers = Ground_level_managers_reg.objects.values_list("phonenumber", flat=True)
        if ground_staff_phonenumbers:
            for phone_number in ground_staff_phonenumbers:
                try:
                    client_twilio.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:+91{phone_number}",
                    content_sid=TWILIO_GLM_TEMPLATE_SID,
                    content_variables=f'{{"1":"{new_property.purpose}", "2":"{new_property.mode_of_property}", "3":"{new_property.district}","4":"{new_property.place}"}}'
                    )
                    print(f"✅ WhatsApp sent to ground staff: +91{phone_number}")
                except Exception as err:
                    print(f"❌ Error sending to ground staff +91{phone_number}: {err}")

            return Response(
                {"message": "⚠️ No matching properties found! WhatsApp notification sent to Ground-Level Staff."},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"message": "⚠️ No matching properties found! Email notification sent to Ground-Level Staff."},
            status=200
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)


    
    
    




@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def databank_graph(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    total_datas = DataBank.objects.filter(stage="Pending").count()
    for_buy = DataBank.objects.filter(purpose='For Buying a Property',stage="Pending").count()
    for_sell = DataBank.objects.filter(purpose='For Selling a Property',stage="Pending").count()
    for_rent = DataBank.objects.filter(purpose='For Rental or Lease',stage="Pending").count()
    rental_seeker = DataBank.objects.filter(purpose='Looking to Rent or Lease Property',stage="Pending").count()

    response_data = {
        "total_collections": total_datas,
        "sell": for_sell,
        "buy": for_buy,
        "for_rental": for_rent,
        "rental_seeker": rental_seeker
    }
    return Response(response_data, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def Buy_databank(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    buy_list = DataBank.objects.filter(purpose = "For Buying a Property",stage="Pending")
    serializer = DataBankGETSerializer(buy_list,many=True).data
    return Response(serializer,status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def Sell_databank(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    buy_list = DataBank.objects.filter(purpose = "For Selling a Property",stage="Pending")
    serializer = DataBankGETSerializer(buy_list,many=True).data
    return Response(serializer,status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def ForRent_databank(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    buy_list = DataBank.objects.filter(purpose = "For Rental or Lease",stage="Pending")
    serializer = DataBankGETSerializer(buy_list,many=True).data
    return Response(serializer,status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def RentSeeker_databank(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    buy_list = DataBank.objects.filter(purpose = "Looking to Rent or Lease Property",stage="Pending")
    serializer = DataBankGETSerializer(buy_list,many=True).data
    return Response(serializer,status=200)




@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def SalesM_Buy_databank(request):
    staff = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    buy_list = DataBank.objects.filter(purpose = "For Buying a Property",stage="Pending",leaddatafollower__follower=salesmanager)
    serializer = DataBankGETSerializer(buy_list,many=True).data
    return Response(serializer,status=200)



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def SalesM_Sell_databank(request):
    staff = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    sell_list = DataBank.objects.filter(purpose = "For Selling a Property",stage="Pending",leaddatafollower__follower=salesmanager)
    serializer = DataBankGETSerializer(sell_list,many=True).data
    return Response(serializer,status=200)




@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def SalesM_ForRent_databank(request):
    staff = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    rental_list = DataBank.objects.filter(purpose = "For Rental or Lease",stage="Pending",leaddatafollower__follower=salesmanager)
    serializer = DataBankGETSerializer(rental_list,many=True).data
    return Response(serializer,status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def SalesM_RentSeeker_databank(request):
    staff = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(staff, 'sales_manager_reg'):
        return Response({"error": "Not a valid sales manager"}, status=403)
    
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    seeker_list = DataBank.objects.filter(purpose = "Looking to Rent or Lease Property",stage="Pending",leaddatafollower__follower=salesmanager)
    serializer = DataBankGETSerializer(seeker_list,many=True).data
    return Response(serializer,status=200)









@api_view(['POST'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def add_image_databank(request,databank_id):
    staff = request.user

    # Check if the user is a sales manager
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the databank entry
    try:
        databank = DataBank.objects.get(id=databank_id, leaddatafollower__follower=salesmanager)
    except DataBank.DoesNotExist:
        return Response({"error": "Databank not available or unauthorized access"}, status=status.HTTP_404_NOT_FOUND)

    # Check if images are present in the request
    images = request.FILES.getlist('photos')  # `getlist` handles multiple images
    if not images:
        return Response({"error": "No images provided"}, status=status.HTTP_400_BAD_REQUEST)

    # Save images
    image_instances = []
    for image in images:
        img_instance = DataBankImage(databank=databank, image=image)
        img_instance.save()
        image_instances.append(img_instance)

    serializer = DataBankImageSerializer(image_instances, many=True)
    return Response(serializer.data, status=status.HTTP_201_CREATED)




@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def view_images_databank(request, databank_id):
    staff = request.user

    # Check if the user is a sales manager
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the databank entry
    try:
        databank = DataBank.objects.get(id=databank_id, leaddatafollower__follower=salesmanager)
    except DataBank.DoesNotExist:
        return Response({"error": "Databank not available or unauthorized access"}, status=status.HTTP_404_NOT_FOUND)


    # Fetch all images for the given databank
    images = DataBankImage.objects.filter(databank=databank)
    if not images.exists():
        return Response({"message": "No images available for this databank"}, status=status.HTTP_404_NOT_FOUND)

    # Serialize and return image data
    serializer = DataBankImageSerializer(images, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)




@api_view(['DELETE'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def delete_image(request, databank_id, image_id):
    staff = request.user

    # Check if the user is a sales manager
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)

    # Check if the databank exists and belongs to the sales manager
    try:
        databank = DataBank.objects.get(id=databank_id, leaddatafollower__follower=salesmanager)
    except DataBank.DoesNotExist:
        return Response({"error": "Databank not available or unauthorized access"}, status=status.HTTP_404_NOT_FOUND)

    # Retrieve the image
    image = get_object_or_404(DataBankImage, id=image_id, databank=databank)

    # Delete the image
    image.delete()
    
    return Response({"message": "Image deleted successfully"}, status=status.HTTP_200_OK)





@api_view(['GET'])
@permission_classes([IsAuthenticated,IsSalesManagerUser])
def salesmanager_databank_graph(request):
    staff = request.user

    # Check if the user is a sales manager
    salesmanager = Sales_manager_reg.objects.filter(user=staff.id).first()
    if not salesmanager:
        return Response({"error": "Not a valid sales manager"}, status=status.HTTP_403_FORBIDDEN)
    total_datas = DataBank.objects.filter( leaddatafollower__follower=salesmanager).count()
    for_buy = DataBank.objects.filter( leaddatafollower__follower=salesmanager, purpose='For Buying a Property',stage="Pending").count()
    for_sell = DataBank.objects.filter( leaddatafollower__follower=salesmanager, purpose='For Selling a Property',stage="Pending").count()
    for_rent = DataBank.objects.filter( leaddatafollower__follower=salesmanager, purpose='For Rental or Lease',stage="Pending").count()
    rental_seeker = DataBank.objects.filter( leaddatafollower__follower=salesmanager, purpose='Looking to Rent or Lease Property',stage="Pending").count()

    response_data = {
        "total_collections": total_datas,
        "sell": for_sell,
        "buy": for_buy,
        "for_rental": for_rent,
        "rental_seeker": rental_seeker
    }
    return Response(response_data, status=200)




@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def admin_single_databank(request,databank_id):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    
    databank = DataBank.objects.filter(id=databank_id)
    serializer = DataBankGETSerializer(databank,many=True).data
    return Response(serializer,status=status.HTTP_200_OK)





@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def admin_view_images_databank(request, databank_id):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the databank entry
    try:
        databank = DataBank.objects.get(id=databank_id)
    except DataBank.DoesNotExist:
        return Response({"error": "Databank not available or unauthorized access"}, status=status.HTTP_404_NOT_FOUND)

    # Fetch all images for the given databank
    images = DataBankImage.objects.filter(databank=databank)
    if not images.exists():
        return Response({"message": "No images available for this databank"}, status=status.HTTP_404_NOT_FOUND)

    # Serialize and return image data
    serializer = DataBankImageSerializer(images, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)












@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def Databank_List_admin(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    databank = DataBank.objects.filter(lead__stage__in=['Pending'])
    serializer = DataBankGETSerializer(databank,many=True).data
    return Response(serializer,status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def Databank(request):
    admin = request.user

    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    # Databank list
    databank_list = DataBank.objects.all()
    serializer = DataBankGETSerializer(databank_list, many=True)

    # Analytics data
    total_datas = databank_list.count(stage="Pending")
    for_buy = databank_list.filter(purpose='For Buying a Property',stage="Pending").count()
    for_sell = databank_list.filter(purpose='For Selling a Property',stage="Pending").count()
    for_rent = databank_list.filter(purpose='For Rental or Lease',stage="Pending").count()
    rental_seeker = databank_list.filter(purpose='Looking to Rent or Lease Property',stage="Pending").count()

    analytics = {
        "total_collections": total_datas,
        "buy": for_buy,
        "sell": for_sell,
        "for_rental": for_rent,
        "rental_seeker": rental_seeker,
    }

    return Response({
        "databank": serializer.data,
        "analytics": analytics
    }, status=200)





@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdminUser])
def Delete_lead(request,lead_id):
    admin_user = request.user

    # Check if the user has the admin profile
    if not hasattr(admin_user, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)
    
    lead = DataBank.objects.filter(id=lead_id).first()
    lead.delete()
    return Response({'message':"lead deleted successfully"})



@api_view(['GET'])
@permission_classes([IsAuthenticated,IsCustomAdminUser])
def Databank_List_admin(request):
    admin = request.user  # `request.user` will be automatically populated with the authenticated user

    # Check if the user is an admin
    if not hasattr(admin, 'admin_reg'):
        return Response({'error': 'Admin authentication required'}, status=status.HTTP_403_FORBIDDEN)

    databank = DataBank.objects.filter(stage__in=['Not Opened','Pending']).filter(projects__isnull=True)
    serializer = DataBankGETSerializer(databank,many=True).data
    return Response(serializer,status=status.HTTP_200_OK)