from django.urls import path

from . import views

urlpatterns = [
    path('', views.slash_command, name='slash_command'),
    path('api-event/', views.event, name='event'),
]
