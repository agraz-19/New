from rest_framework import serializers
from .models import Employee

ALLOWED_DESIGNATIONS = {
    "Scientist-F",
    "Scientist-G",
    "Scientist-E",
    "Scientist-D",
    "Scientist-C",
    "Scientist-B",
    "Section Officer",
    "Senior Secretariate Assistant",
    "Scientific/Technical Assistant-A",
    "Scientific/Technical Assistant-B",
    "Scientific Officer/Engineer-SB",
}

class EmployeeSerializer(serializers.ModelSerializer):
    super_annuation_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Employee
        exclude = ['encrypted_super_annuation_date']

    def validate_designation(self, value):
        if not value:
            return value # Allow empty if user cannot set it
        
        value = value.strip()
        if value and value not in ALLOWED_DESIGNATIONS:
            if len(value) < 3:
                raise serializers.ValidationError("Custom designation is too short")
        return value

    def validate(self, attrs):
        if attrs.get("status") == "submitted":
            # REMOVED 'designation' from this list
            required_fields = ["empcode", "ename", "hname"] 
            for field in required_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        f"{field} is required before submission"
                    )
        return attrs
    def create(self, validated_data):
        # Extract the date safely
        date_value = validated_data.pop('super_annuation_date', None)
        
        # Create the object without the date first
        instance = Employee.objects.create(**validated_data)
        
        # Manually encrypt and save the date if it exists
        if date_value:
            instance.set_super_annuation_date(date_value)
            instance.save()
        return instance

    def update(self, instance, validated_data):
        # Check if 'super_annuation_date' is in the request (even if None)
        if 'super_annuation_date' in validated_data:
            date_value = validated_data.pop('super_annuation_date')
            # This handles both setting a new date AND clearing it (None)
            instance.set_super_annuation_date(date_value)

        # Standard update for the rest of the fields
        return super().update(instance, validated_data)
