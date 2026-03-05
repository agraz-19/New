
from django.contrib import admin
from django.urls import path, include
from captcha import views as captcha_views # <--- Add this import

urlpatterns = [
    path('admin/', admin.site.urls),

    # frontend urls
    path('', include('website.urls')),
    path('captcha/', include('captcha.urls')),
path('captcha/refresh/', captcha_views.captcha_refresh, name='captcha-refresh'),    


]
handler400 = 'website.views.error_400'
handler403 = 'website.views.error_403'
handler404 = 'website.views.error_404'
handler500 = 'website.views.error_500'