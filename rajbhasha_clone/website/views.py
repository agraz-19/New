from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Employee
from .forms import EmployeeForm  # Import the form class for Employee model

# Home view
def home(request):
    return render(request, "home.html")

# API Views for Employee CRUD operations
@api_view(['GET'])
def get_users(request):
    employees = Employee.objects.all()  # Retrieve all employees
    serializer = EmployeeSerializer(employees, many=True)  # Serialize employee data
    return Response(serializer.data)

@api_view(['POST'])
def create_user(request):
    serializer = EmployeeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()  # Save the employee data to the database
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def user_detail(request, pk):
    try:
        employee = Employee.objects.get(pk=pk)
    except Employee.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = EmployeeSerializer(employee)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = EmployeeSerializer(employee, data=request.data)
        if serializer.is_valid():
            serializer.save()  # Save the updated employee data
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        employee.delete()  # Delete the employee from the database
        return Response(status=status.HTTP_204_NO_CONTENT)

        employee.delete()
        return Response({"message": "Employee deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

# Bootstrap UI Views

# Display all employees saved as drafts
def user_list_ui(request):
    employees = Employee.objects.all()  # Retrieve all employees saved as drafts
    return render(request, 'user_form.html', {
        'employees': employees
    })


# Add a new employee (draft)
def add_user_ui(request):
    if request.method == 'POST':
        # Saving the form data
        empcode = request.POST.get('empcode')
        ename = request.POST.get('ename')
        hname = request.POST.get('hname')
        desig = request.POST.get('desig')
        gazet = request.POST.get('gazet')
        prabodh = request.POST.get('prabodh')
        praveen = request.POST.get('praveen')
        pragya = request.POST.get('pragya')
        parangat = request.POST.get('parangat')
        typing = request.POST.get('typing')
        hindiproficiency = request.POST.get('hindiproficiency')
        lastupdate = request.POST.get('lastupdate')
        superannuationDate = request.POST.get('superannuationDate')
        
        # Save data as a draft
        employee = Employee.objects.create(
            empcode=empcode,
            ename=ename,
            hname=hname,
            desig=desig,
            gazet=gazet,
            prabodh=prabodh,
            praveen=praveen,
            pragya=pragya,
            parangat=parangat,
            typing=typing,
            hindiproficiency=hindiproficiency,
            lastupdate=lastupdate,
            superannuationDate=superannuationDate
        )
        return redirect('user_list_ui')  # Redirect after saving the draft

    return render(request, 'user_form.html')


# Edit employee data
def edit_user_ui(request, pk):
    employee = Employee.objects.get(pk=pk)

    if request.method == 'POST':
        employee.empcode = request.POST['empcode']
        employee.ename = request.POST['ename']
        employee.hname = request.POST['hname']
        employee.desig = request.POST['desig']
        employee.gazet = request.POST['gazet']
        employee.prabodh = request.POST['prabodh']
        employee.praveen = request.POST['praveen']
        employee.pragya = request.POST['pragya']
        employee.parangat = request.POST['parangat']
        employee.typing = request.POST['typing']
        employee.hindiproficiency = request.POST['hindiproficiency']
        employee.lastupdate = request.POST['lastupdate']
        employee.superannuationDate = request.POST['superannuationDate']
        employee.save()
        return redirect('user_list_ui')

    return render(request, 'user_form.html', {'employee': employee})


# Delete employee data
def delete_user_ui(request, pk):
    employee = Employee.objects.get(pk=pk)
    employee.delete()
    return redirect('user_list_ui')
