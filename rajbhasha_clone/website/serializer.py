from rest_framework import serializers
from .models import Employee  # Import the Employee model

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee  # The model to serialize
        fields = '__all__'  # Include all fields in the model
