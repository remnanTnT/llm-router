from django.urls import path, re_path

from router import views

urlpatterns = [
    path("healthy", views.healthy),
    path("api/whitelist/update", views.whitelist_update),
    path("api/refresh_user_info", views.refresh_user_info),
    re_path(r"^v1/(?P<path>.*)$", views.proxy),
]
