import django_filters
from django.db.models import Q
from .models import DataBank
class DataBankFilter(django_filters.FilterSet):
    district = django_filters.CharFilter(lookup_expr='icontains')
    place = django_filters.CharFilter(lookup_expr='icontains')
    location_preferences = django_filters.CharFilter(method='filter_location_preferences')
    purpose = django_filters.CharFilter(lookup_expr='icontains')
    mode_of_property = django_filters.CharFilter(lookup_expr='icontains')
    lead_category = django_filters.CharFilter(lookup_expr='icontains')
    building_roof = django_filters.CharFilter(lookup_expr='icontains')

    demand_price_min = django_filters.NumberFilter(field_name="demand_price", lookup_expr='gte')
    demand_price_max = django_filters.NumberFilter(field_name="demand_price", lookup_expr='lte')

    advance_price_min = django_filters.NumberFilter(field_name="advance_price", lookup_expr='gte')
    advance_price_max = django_filters.NumberFilter(field_name="advance_price", lookup_expr='lte')

    area_in_sqft = django_filters.CharFilter(lookup_expr='icontains')
    area_in_cent = django_filters.CharFilter(lookup_expr='icontains')
    number_of_floors = django_filters.CharFilter(lookup_expr='icontains')
    building_bhk = django_filters.CharFilter(lookup_expr='icontains')

    timestamp = django_filters.DateFromToRangeFilter()

    class Meta:
        model = DataBank
        fields = [
            'district', 'place', 'location_preferences', 'purpose', 'mode_of_property', 'lead_category',
            'building_roof', 'area_in_sqft', 'area_in_cent', 'number_of_floors',
            'building_bhk', 'timestamp',
        ]

    def filter_location_preferences(self, queryset, name, value):
        """
        Custom filter to check if any of the comma-separated values in `value`
        matches any of the comma-separated locations in the model field `location_preferences`.
        """
        if not value:
            return queryset
        
        # Split user input locations by comma, strip spaces, lowercase for case-insensitive matching
        filter_places = [p.strip().lower() for p in value.split(',') if p.strip()]
        
        # Build Q object with OR condition for each place, checking if the model field contains that place (case-insensitive)
        query = Q()
        for place in filter_places:
            # We check if the place is contained in location_preferences (case-insensitive)
            query |= Q(location_preferences__icontains=place)
        
        return queryset.filter(query)
