from rest_framework import serializers


class CrunchBaseOrganizationSerializer(serializers.Serializer):
    cb_url_field_name=serializers.CharField()
    cb_uuid_field_name=serializers.CharField()
    company_prev_raised_count_field_name=serializers.CharField()
    company_total_raised_value_field_name=serializers.CharField()
    cb_updated_at=serializers.CharField()


class CrunchBaseFounderSerializer(serializers.Serializer):
    cb_url_field_name = serializers.CharField()
    cb_uuid_field_name = serializers.CharField()
    organization_of_interest_field_name=serializers.CharField()
    org_founder_map_founding_date_field_name=serializers.CharField()
    company_prev_raised_count_field_name=serializers.CharField()
    company_total_raised_value_field_name=serializers.CharField()
