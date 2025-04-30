from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import UserRegisterForm

def index(request):
    return render(request, 'game/index.html')

def room(request, room_name):
    return render(request, 'game/room.html', {
        'room_name': room_name
    })

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 設置顯示名稱
            user.profile.display_name = form.cleaned_data.get('display_name')
            user.profile.save()
            
            login(request, user)  # 註冊後自動登入
            return redirect('index')
    else:
        form = UserRegisterForm()
    return render(request, 'registration/register.html', {'form': form})
