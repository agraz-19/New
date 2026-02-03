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
        fields = "__all__"
