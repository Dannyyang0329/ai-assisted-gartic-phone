document.addEventListener('DOMContentLoaded', function() {
    // 設置範例房間
    const recentRooms = ['創意空間', '夢境畫布', '藝術時光', '色彩實驗', '靈感工坊'];
    const recentRoomsList = document.getElementById('recent-rooms-list');
    
    if (recentRooms.length > 0) {
        recentRooms.forEach(room => {
            const li = document.createElement('li');
            li.className = 'room-item';
            li.innerHTML = `<span class="room-item-icon"></span>${room}`;
            
            // 加入動畫效果
            li.style.animation = 'fadeInUp 0.5s ease forwards';
            li.style.animationDelay = (0.1 * recentRooms.indexOf(room)) + 's';
            
            li.onclick = function() {
                const input = document.getElementById('room-name-input');
                input.value = room;
                input.focus();
                
                // 添加視覺反饋
                li.style.backgroundColor = 'var(--secondary)';
                li.style.color = 'white';
                
                // 移除自動提交，僅填充輸入框
                setTimeout(() => {
                    li.style.backgroundColor = ''; 
                    li.style.color = '';
                }, 300);
            };
            recentRoomsList.appendChild(li);
        });
    }
    
    // 輸入框事件處理
    document.querySelector('#room-name-input').addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            document.querySelector('#room-name-submit').click();
        }
    });
    
    // 用戶 ID 輸入事件處理
    const userIdInput = document.querySelector('#user-id-input');
    const userIdStatus = document.querySelector('#userid-status');
    const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
    const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
    
    let checkTimeout = null;
    
    userIdInput.addEventListener('input', function() {
        const userId = this.value.trim();
        
        // 清除之前的超時
        if (checkTimeout) {
            clearTimeout(checkTimeout);
        }
        
        // 重置狀態區域
        userIdStatus.className = 'userid-status visible checking';
        userIdStatusIcon.textContent = '?';
        userIdStatusText.textContent = '檢查中...';
        
        // 如果用戶 ID 為空，隱藏狀態
        if (!userId) {
            userIdStatus.className = 'userid-status';
            return;
        }
        
        // 設置延遲以避免頻繁請求
        checkTimeout = setTimeout(() => {
            // 修改為正確的URL路徑，確保含有完整路徑
            fetch(`/game/check-userid/?userid=${encodeURIComponent(userId)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.available) {
                        userIdStatus.className = 'userid-status visible available';
                        userIdStatusIcon.textContent = '✓';
                        userIdStatusText.textContent = data.message;
                    } else {
                        userIdStatus.className = 'userid-status visible unavailable';
                        userIdStatusIcon.textContent = '✗';
                        userIdStatusText.textContent = data.message;
                    }
                })
                .catch(error => {
                    console.error('檢查用戶 ID 時出錯:', error);
                    userIdStatus.className = 'userid-status visible unavailable';
                    userIdStatusIcon.textContent = '!';
                    userIdStatusText.textContent = '檢查時發生錯誤';
                });
        }, 500); // 500ms 延遲，避免頻繁請求
    });
    
    // 提交按鈕事件處理
    document.querySelector('#room-name-submit').addEventListener('click', function() {
        const roomInput = document.querySelector('#room-name-input');
        const userIdInput = document.querySelector('#user-id-input');
        const roomName = roomInput.value.trim();
        const userId = userIdInput.value.trim();
        
        // 驗證房間名稱
        if (roomName === '') {
            showTooltip(roomInput, '請輸入房間名稱');
            roomInput.focus();
            return;
        }
        
        // 驗證用戶ID
        if (userId === '') {
            showTooltip(userIdInput, '請輸入您的ID');
            userIdInput.focus();
            return;
        }
        
        // 移除僅限英文字母的限制，允許中文
        if (roomName.length > 20) {
            showTooltip(roomInput, '房間名稱不得超過20個字');
            roomInput.focus();
            return;
        }
        
        // 檢查用戶 ID 是否合法
        if (userIdStatus.classList.contains('unavailable')) {
            showTooltip(userIdInput, userIdStatusText.textContent);
            userIdInput.focus();
            return;
        }
        
        // 顯示加載動畫
        this.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite">⟳</span>';
        this.disabled = true;
        
        // 重定向到房間頁面
        setTimeout(() => {
            window.location.href = `/waiting_room/${encodeURIComponent(roomName)}/?userid=${encodeURIComponent(userId)}`;
        }, 400);
    });
    
    // 工具提示函數
    function showTooltip(element, message) {
        // 移除舊的工具提示
        const oldTooltip = document.querySelector('.tooltip-error');
        if (oldTooltip) {
            oldTooltip.remove();
        }
        
        // 創建新的工具提示
        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip-error';
        tooltip.textContent = message;
        
        // 放置工具提示
        element.parentNode.style.position = 'relative';
        element.parentNode.appendChild(tooltip);
        
        // 計算位置
        tooltip.style.top = element.offsetHeight + 8 + 'px';
        tooltip.style.left = '0';
        
        // 3秒後自動消失
        setTimeout(() => {
            tooltip.style.animation = 'fadeOut 0.3s forwards';
            setTimeout(() => {
                if (tooltip.parentNode) {
                    tooltip.parentNode.removeChild(tooltip);
                }
            }, 300);
        }, 3000);
    }
});
