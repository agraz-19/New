
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from captcha import views as captcha_views # <--- Add this import

urlpatterns = [
    #path('admin/', admin.site.urls), #this is the default django admin page. To implement it comment out this line

    # frontend urls
    path('', include('website.urls')),
    path('captcha/', include('captcha.urls')),
    path('captcha/refresh/', captcha_views.captcha_refresh, name='captcha-refresh'),    


]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler400 = 'website.views.error_400'
handler403 = 'website.views.error_403'
handler404 = 'website.views.error_404'
handler500 = 'website.views.error_500'