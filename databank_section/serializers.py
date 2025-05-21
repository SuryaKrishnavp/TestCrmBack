from rest_framework import serializers
from .models import DataBank,DataBankImage,LeadDataFollower

from auth_section.models import Sales_manager_reg






        
class DataBankSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataBank
        fields = '__all__'

    
    
class DataBankEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataBank
        fields = '__all__' 
        
        
        
class DataBankGETSerializer(serializers.ModelSerializer):
    follower_name = serializers.CharField(source='follower.username', read_only=True)
    is_in_project = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()

    class Meta:
        model = DataBank
        fields = '__all__'
        extra_fields = ['is_in_project', 'project_name']

    def get_is_in_project(self, obj):
        return obj.projects.exists()

    def get_project_name(self, obj):
        first_project = obj.projects.first()
        return first_project.project_name if first_project else None

        
class DataBankImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataBankImage
        fields = ['id', 'image']
        
        
        
class SalesManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sales_manager_reg
        fields = ['id', 'username']  # Adjust 'name' to your follower name field

class LeadDataFollowerSerializer(serializers.ModelSerializer):
    follower = SalesManagerSerializer(read_only=True)

    class Meta:
        model = LeadDataFollower
        fields = ['follower']

class DataBankViewSerializer(serializers.ModelSerializer):
    followers = serializers.SerializerMethodField()  # This is NOT a DB field!

    class Meta:
        model = DataBank
        fields = [
            'timestamp','id', 'name', 'phonenumber', 'district', 'place',
            'purpose', 'mode_of_property', 'demand_price', 'advance_price',
            'area_in_sqft', 'area_in_cent', 'building_roof', 'number_of_floors',
            'building_bhk', 'additional_note', 'location_link', 'lead_category',
            'image_folder', 'status', 'stage', 'closed_date', 'care_of',
            'followers',  # Include the computed followers field here
        ]

    def get_followers(self, obj):
        related_followers = LeadDataFollower.objects.filter(lead=obj)
        return LeadDataFollowerSerializer(related_followers, many=True).data
    
class AdminDataBankSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataBank
        exclude = ["timestamp", "status", "stage", "closed_date"]