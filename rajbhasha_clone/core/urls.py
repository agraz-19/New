
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # frontend urls
    path('', include('website.urls')),

]
