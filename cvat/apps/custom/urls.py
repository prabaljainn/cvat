# Copyright (C) 2025 CVAT Custom Module
# SPDX-License-Identifier: MIT

from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views
from . import views_optimized
from . import views_cvat_integrated
from . import views_task_analysis
from . import views_train_metadata
from . import views_task_extension
from . import views_analytics

# Create a router for our extended task endpoints
router = DefaultRouter(trailing_slash=False)
router.register('tasks-extended', views_task_extension.ExtendedTaskViewSet, basename='tasks-extended')

urlpatterns = [
    # Frame download endpoints
    path('download-annotated-frames/', views.DownloadAnnotatedFramesView.as_view(),
         name='download-annotated-frames'),
    path('download-task-frames/', views.DownloadTaskFramesView.as_view(),
         name='download-task-frames'),
    path('download-task-frames-optimized/', views_optimized.OptimizedDownloadTaskFramesView.as_view(),
         name='download-task-frames-optimized'),
    path('export-task/', views_cvat_integrated.CVATIntegratedExportView.as_view(),
         name='cvat-integrated-export'),
    path('formats/', views_cvat_integrated.CVATFormatsListView.as_view(),
         name='export-formats'),

    # Task analysis endpoints
    path('task-analysis/', views_task_analysis.TaskAnalysisView.as_view(),
         name='task-analysis'),

    # Train metadata endpoints
    path('train-metadata/', views_train_metadata.TrainMetadataView.as_view(),
         name='train-metadata'),
    path('update-verdict/', views_train_metadata.TrainVerdictUpdateView.as_view(),
         name='update-verdict'),
    path('train-metadata-list/', views_train_metadata.TrainMetadataListView.as_view(),
         name='train-metadata-list'),

    # Task extension endpoints (for UI integration)
    path('tasks/<int:pk>/train-metadata/', views_task_extension.TaskTrainMetadataAPIView.as_view(),
         name='task-train-metadata'),
    path('tasks/<int:pk>/verdict/', views_task_extension.TaskVerdictUpdateAPIView.as_view(),
         name='task-verdict-update'),

    # Analytics and reporting endpoints
    path('train-analytics/', views_analytics.TrainAnalyticsView.as_view(),
         name='train-analytics'),
    path('tasks-paginated/', views_analytics.TasksPaginatedView.as_view(),
         name='tasks-paginated'),
    path('tasks-quick-stats/', views_analytics.TasksQuickStatsView.as_view(),
         name='tasks-quick-stats'),
]

# Add the router URLs
urlpatterns += router.urls
