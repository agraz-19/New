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
    super_annuation_date = serializers.DateField(
        format="%Y-%m-%d",  # Output format (for frontend)
        input_formats=["%Y-%m-%d"], # Input format (from frontend)
        required=False, 
        allow_null=True
    )

    def validate_designation(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Designation cannot be empty")

        # Allow predefined OR custom (Other)
        if value not in ALLOWED_DESIGNATIONS:
            if len(value) < 3:
                raise serializers.ValidationError(
                    "Custom designation is too short"
                )
        return value

    def validate(self, attrs):
        if attrs.get("status") == "submitted":
            required_fields = ["empcode", "ename", "hname", "designation"]
            for field in required_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        f"{field} is required before submission"
                    )
        return attrs

    class Meta:
        model = Employee
        # List all fields explicitly to avoid including the encrypted binary field
        fields = [
            'id', 'empcode', 'ename', 'hname', 'designation', 
            'gazet', 'prabodh', 'praveen', 'pragya', 'parangat',
            'typing', 'hindiproficiency', 'status', 'lastupdate',
            'super_annuation_date' # This maps to your model property
        ]
