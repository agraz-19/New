import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from deep_translator import GoogleTranslator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .employeeform import EmployeeForm
from .models import Employee
from .serializers import EmployeeSerializer

# ================= FRONTEND VIEWS =================

def home(request):
    return render(request, "home.html")

def employee_form(request):
    """
    Renders the employee HTML form.
    Form submission is handled via JS + DRF API.
    """
    form = EmployeeForm()
    return render(request, "someform.html", {"form": form})

# ================= AUTOMATED TRANSLATION API =================

@csrf_exempt
def translate_api(request):
    """
    Mimics Google Translate behavior using deep-translator.
    Processes dynamic table data for 100% automated localization.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            text = data.get("text", "")
            target = data.get("target", "hi")
            
            # Return immediately for empty fields or placeholders
            if not text or text == "-":
                return JsonResponse({"translated": text})
            
            # Automated translation for any new user-entered data
            translated = GoogleTranslator(source='auto', target=target).translate(text)
            return JsonResponse({"translated": translated})
            
        except Exception as e:
            return JsonResponse({"translated": text, "error": str(e)})
    
    return JsonResponse({"error": "Invalid request method"}, status=405)

# ================= REST API VIEWS =================

class EmployeeListCreateAPI(APIView):
    def get(self, request):
        status_filter = request.GET.get("status")
        qs = Employee.objects.all()

        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = EmployeeSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmployeeDetailAPI(APIView):
    def get_object(self, pk):
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return None

    def get(self, request, pk):
        employee = self.get_object(pk)
        if not employee:
            return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = EmployeeSerializer(employee)
        return Response(serializer.data)

    def put(self, request, pk):
        employee = self.get_object(pk)
        if not employee:
            return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = EmployeeSerializer(employee, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        employee = self.get_object(pk)
        if not employee:
            return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
        employee.delete()
        return Response({"message": "Employee deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

class SubmitDraftAPI(APIView):
    def post(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response(
                {"error": "No drafts selected"},
                status=status.HTTP_400_BAD_REQUEST
            )
        Employee.objects.filter(id__in=ids, status="draft").update(status="submitted")
        return Response({"message": "Drafts submitted successfully"})