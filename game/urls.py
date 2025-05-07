from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('<str:room_name>/', views.waiting_room, name='waiting_room'),
    path('<str:room_name>/game/', views.room, name='room'),
]
