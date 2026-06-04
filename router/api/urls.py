from django.urls import path

from router import views as router_views
from router.api import views

urlpatterns = [
    path("request_stats", views.request_stats),
    path("total_request_count", views.total_request_count),
    path("model_request_stats", views.model_request_stats),
    path("all_model_request_stats", views.all_model_request_stats),
    path("models", views.models),
    path("model_info", views.model_info),
    path("request_time_stats", views.request_time_stats),
    path("model_request_time_stats", views.model_request_time_stats),
    path("model_request_count_by_period", views.model_request_count_by_period),
    path("model_ip_count_by_period", views.model_ip_count_by_period),
    path("model_latency_boxplot", views.model_latency_boxplot),
    path("download/ai_assistant", views.download_ai_assistant),
    path("whitelist/update", router_views.whitelist_update),
    path("refresh_user_info", router_views.refresh_user_info),
    path("add_server", views.add_server),
    path("mr_live_review", views.upsert_mr_live_review),
    path("mr_live_review/stats", views.mr_live_review_stats),
    path("mr_live_review/stats_by_confidence", views.mr_live_review_stats_by_confidence),
    path("mr_live_review/stats_by_date", views.mr_live_review_stats_by_date),
    path("mr_live_review/list", views.mr_live_review_list),
    path("mr_live_review/list_by_confidence", views.mr_live_review_list_by_confidence),
    path("codehub_review", views.create_codehub_review),
]
