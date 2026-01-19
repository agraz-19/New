from django.urls import path
from . import views   # Import your views.py

urlpatterns = [
    # Homepage route
    path('', views.home, name='home'),  # Add this line for the homepage
    
    # API URLs
    path('users/', views.get_users, name='get_users'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),

    # UI URLs
    path('ui/users/', views.user_list_ui, name='user_list_ui'),
    path('ui/users/add/', views.add_user_ui, name='add_user_ui'),
    path('ui/users/edit/<int:pk>/', views.edit_user_ui, name='edit_user_ui'),
    path('ui/users/delete/<int:pk>/', views.delete_user_ui, name='delete_user_ui'),
]
