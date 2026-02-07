from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, DataAccessLog

# Register CustomUser using the built-in UserAdmin for full functionality
admin.site.register(CustomUser, UserAdmin)
admin.site.register(DataAccessLog)
# Register the Privacy Audit Log so you can see it in Admin
'''@admin.register(DataAccessLog)
class DataAccessLogAdmin(admin.ModelAdmin):
    list_display = ('accessed_by', 'target_user', 'access_time', 'reason')
    readonly_fields = ('access_time',) # DPDP Audit logs should not be editable'''