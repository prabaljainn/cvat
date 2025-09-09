# Copyright (C) 2025 CVAT Custom Module
# SPDX-License-Identifier: MIT

from django.urls import path
from . import views

urlpatterns = [
    path('download-annotated-frames/', views.DownloadAnnotatedFramesView.as_view(),
         name='download-annotated-frames'),
    path('download-task-frames/', views.DownloadTaskFramesView.as_view(),
         name='download-task-frames'),
]
