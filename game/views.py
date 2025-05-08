from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.models import User
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
import logging
import json

# 全局集合來存儲活躍的訪客用戶ID
active_guest_ids = set()

# 設置日誌
logger = logging.getLogger(__name__)

def index(request):
    # 檢查是否有重定向參數
    redirect_room = request.GET.get('redirect_room', '')
    
    context = {
        'redirect_room': redirect_room,
    }
    
    return render(request, 'game/index.html', context)

def room(request, room_name):
    # Get the user ID from sessionStorage
    userid = request.POST.get('userid', '') or request.headers.get('X-User-Id', '')
    
    # 如果沒有用戶ID或ID不符合要求，重定向到主頁面
    if not userid:
        logger.info(f"room視圖: 未提供用戶ID，重定向到主頁")
        return redirect(f'/?redirect_room={room_name}')
    
    return render(request, 'game/room.html', {
        'room_name': room_name
    })

def waiting_room(request, room_name):
    return render(request, 'game/waiting_room.html', {
        'room_name': room_name
    })

@require_POST
@csrf_exempt  # 注意：在生產環境中應該適當處理CSRF保護
def register_user_id(request):
    """註冊從sessionStorage提交的用戶ID"""
    try:
        data = json.loads(request.body)
        user_id = data.get('userid', '')
        room_name = data.get('room_name', '')
        
        if not user_id:
            return JsonResponse({'success': False, 'message': '未提供用戶ID'}, status=400)
        
        # 檢查用戶ID是否已存在
        exists_in_db = User.objects.filter(username=user_id).exists()
        exists_in_active = user_id in active_guest_ids
        
        if exists_in_db or exists_in_active:
            return JsonResponse({'success': False, 'message': '此用戶ID已被使用'}, status=409)
        
        # 若ID可用，則將其添加到活躍ID集合中
        active_guest_ids.add(user_id)
        logger.info(f"register_user_id: 已添加用戶ID {user_id}, 當前活躍IDs: {active_guest_ids}")
        return JsonResponse({'success': True, 'message': '用戶ID註冊成功'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': '無效的請求格式'}, status=400)

@require_GET
def check_userid_availability(request):
    """檢查用戶 ID 是否可用"""
    userid = request.GET.get('userid', '')
    
    if not userid:
        return JsonResponse({'available': False, 'message': '請輸入用戶 ID'})
    
    # 檢查長度
    if len(userid) < 3:
        return JsonResponse({'available': False, 'message': '用戶 ID 至少需要 3 個字符'})
    
    if len(userid) > 20:
        return JsonResponse({'available': False, 'message': '用戶 ID 不能超過 20 個字符'})
    
    # 檢查是否已存在於用戶表中
    exists_in_db = User.objects.filter(username=userid).exists()
    
    # 檢查是否已存在於活躍訪客ID中
    exists_in_active = userid in active_guest_ids
    
    logger.debug(f"check_userid_availability: 檢查ID {userid}, exists_in_db={exists_in_db}, exists_in_active={exists_in_active}, active_ids={active_guest_ids}")
    
    if exists_in_db or exists_in_active:
        return JsonResponse({'available': False, 'message': '此 ID 已被使用'})
    else:
        return JsonResponse({'available': True, 'message': '此 ID 可用'})
