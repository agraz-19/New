from django.apps import AppConfig


class QprAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qpr_app'

    def ready(self):
        import qpr_app.signals
