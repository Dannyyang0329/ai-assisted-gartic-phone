"""
URL configuration for gartic_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from game import views as game_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', game_views.index, name='index'),  # 根路徑指向index頁面
    path('waiting_room/<str:room_name>/', game_views.waiting_room, name='waiting_room'),
    path('room/<str:room_name>/', game_views.room, name='room'),
    path('game/check-userid/', game_views.check_userid_availability, name='game_check_userid'),
    path('game/register-user-id/', game_views.register_user_id, name='register_user_id'),
    path('game/', include('game.urls')),
]
