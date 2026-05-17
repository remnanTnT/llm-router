from django.urls import include, path, re_path

from router import views

urlpatterns = [
    path("healthy", views.healthy),
    path("api/", include("router.api.urls")),
    re_path(r"^v1/(?P<path>.*)$", views.proxy),
]
