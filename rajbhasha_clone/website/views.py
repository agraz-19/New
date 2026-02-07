import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now

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
    form = EmployeeForm()
    return render(request, "employeeform.html", {"form": form})

def qpr_form_view(request):
    return render(request, "qpr_form.html")


# ================= TRANSLATION API =================

@csrf_exempt
def translate_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        text = data.get("text", "")
        target = data.get("target", "hi")

        if not text or text == "-":
            return JsonResponse({"translated": text})

        translated = GoogleTranslator(source="auto", target=target).translate(text)
        return JsonResponse({"translated": translated})

    return JsonResponse({"error": "Invalid request"}, status=400)


# ================= REST APIs =================

class EmployeeListCreateAPI(APIView):
    def get(self, request):
        status_filter = request.GET.get("status")

        qs = Employee.objects.all()

        if status_filter:
            qs = qs.filter(status=status_filter)

        # 🔥 MOST RECENT FIRST
        qs = qs.order_by("-lastupdate")

        serializer = EmployeeSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(lastupdate=now())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmployeeDetailAPI(APIView):
    def get_object(self, pk):
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return None

    def get(self, request, pk):
        emp = self.get_object(pk)
        if not emp:
            return Response({"error": "Not found"}, status=404)
        return Response(EmployeeSerializer(emp).data)

    def put(self, request, pk):
        emp = self.get_object(pk)
        if not emp:
            return Response({"error": "Not found"}, status=404)

        serializer = EmployeeSerializer(emp, data=request.data)
        if serializer.is_valid():
            serializer.save(lastupdate=now())
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        emp = self.get_object(pk)
        if not emp:
            return Response({"error": "Not found"}, status=404)
        emp.delete()
        return Response({"message": "Deleted"})


class SubmitDraftAPI(APIView):
    def post(self, request):
        ids = request.data.get("ids", [])

        if not ids:
            return Response(
                {"error": "No records selected"},
                status=status.HTTP_400_BAD_REQUEST
            )

        count = Employee.objects.filter(
            id__in=ids,
            status="draft"
        ).update(
            status="submitted",
            lastupdate=now()
        )

        return Response(
            {"message": f"{count} record(s) submitted successfully"},
            status=status.HTTP_200_OK
        )
