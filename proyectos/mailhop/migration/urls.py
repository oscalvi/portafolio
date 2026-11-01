from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new/", views.new_migration, name="new_migration"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/start/", views.job_start, name="job_start"),
    path("jobs/<int:pk>/cancel/", views.job_cancel, name="job_cancel"),
    path("jobs/<int:pk>/progress/", views.job_progress, name="job_progress"),
]
