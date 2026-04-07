import environ
from api.api import ninja_api
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

env = environ.Env()
environ.Env.read_env()

admin.site.site_header = env("SITE_NAME")
admin.site.site_title = env("SITE_NAME")
admin.site.index_title = "Admin Panel"

urlpatterns = [
    path("illiad/", admin.site.urls),
    path("api/v1/", ninja_api.urls),
    path("docs/", include("guides.urls")),
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += debug_toolbar_urls()
