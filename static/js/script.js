document.addEventListener('DOMContentLoaded', function() {
    // 設置範例房間
    const recentRooms = ['創意空間', '夢境畫布', '藝術時光', '色彩實驗', '靈感工坊'];
    const recentRoomsList = document.getElementById('recent-rooms-list');
    
    if (recentRoomsList && recentRooms.length > 0) {
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
    
    // 檢查URL參數
    const urlParams = new URLSearchParams(window.location.search);
    const errorType = urlParams.get('error');
    const rejectedUserId = urlParams.get('userid');
    const redirectRoom = urlParams.get('redirect_room');
    const roomType = urlParams.get('room_type');
    
    // 處理從其他頁面重定向過來的請求
    if (redirectRoom) {
        const roomInput = document.getElementById('room-name-input');
        if (roomInput) {
            roomInput.value = redirectRoom;
        }
        
        // 顯示提示，指示用戶需要輸入ID
        const userIdInput = document.querySelector('#user-id-input');
        if (userIdInput && !rejectedUserId) {
            // 如果沒有被拒絕的用戶ID，聚焦到用戶ID輸入框
            userIdInput.focus();
            userIdInput.classList.add('highlight');
            
            // 3秒後移除高亮效果
            setTimeout(() => {
                userIdInput.classList.remove('highlight');
            }, 3000);
            
            // 顯示提示信息
            const userIdStatus = document.querySelector('#userid-status');
            if (userIdStatus) {
                const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                userIdStatus.className = 'userid-status visible';
                userIdStatusText.textContent = '請輸入一個用戶ID以繼續';
            }
        }
    }
    
    // 處理錯誤消息
    if (errorType) {
        const userIdInput = document.querySelector('#user-id-input');
        const userIdStatus = document.querySelector('#userid-status');
        const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
        const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
        
        userIdStatus.className = 'userid-status visible unavailable';
        userIdStatusIcon.textContent = '✗';
        
        if (errorType === 'userid_taken' && rejectedUserId) {
            // 如果有用戶ID被拒絕的錯誤
            userIdInput.value = rejectedUserId;
            userIdStatusText.textContent = '此ID已被其他人使用';
        } else if (errorType === 'invalid_length') {
            // 如果用戶ID長度不符合要求
            userIdStatusText.textContent = '用戶ID長度必須在3-20個字符之間';
        }
        
        // 聚焦到用戶ID輸入框
        userIdInput.focus();
        userIdInput.classList.add('highlight');
        
        // 3秒後移除高亮效果
        setTimeout(() => {
            userIdInput.classList.remove('highlight');
        }, 3000);
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
        const submitButton = this;
        
        // 驗證房間名稱
        if (roomName === '') {
            showTooltip(roomInput, '請輸入房間名稱');
            roomInput.focus();
            return;
        }
        
        // 驗證用戶ID
        if (userId === '') {
            // 顯示錯誤提示
            const userIdStatus = document.querySelector('#userid-status');
            if (userIdStatus) {
                const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                userIdStatus.className = 'userid-status visible unavailable';
                userIdStatusText.textContent = '請輸入一個用戶ID';
            }
            userIdInput.focus();
            return;
        }
        
        // 檢查URL參數中是否有重定向類型
        const redirectRoomType = document.getElementById('redirect-room-type').value || 'waiting_room';
        
        // 構建URL
        let url;
        if (redirectRoomType === 'room') {
            url = `/room/${encodeURIComponent(roomName)}/?userid=${encodeURIComponent(userId)}`;
        } else {
            url = `/waiting_room/${encodeURIComponent(roomName)}/?userid=${encodeURIComponent(userId)}`;
        }
        
        // 檢查ID是否可用，然後跳轉
        submitButton.innerHTML = '檢查中...';
        submitButton.disabled = true;
        
        fetch(`/game/check-userid/?userid=${encodeURIComponent(userId)}`)
            .then(response => response.json())
            .then(data => {
                if (data.available) {
                    // ID依然可用，繼續提交
                    window.location.href = url;
                } else {
                    // ID已不可用，顯示錯誤信息
                    submitButton.innerHTML = '開始創作';
                    submitButton.disabled = false;
                    
                    // 更新用戶ID狀態顯示
                    const userIdStatus = document.querySelector('#userid-status');
                    if (userIdStatus) {
                        const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
                        const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                        userIdStatus.className = 'userid-status visible unavailable';
                        userIdStatusIcon.textContent = '✗';
                        userIdStatusText.textContent = '此 ID 已被其他人使用';
                    }
                    
                    // 聚焦到用戶ID輸入框
                    userIdInput.focus();
                }
            })
            .catch(error => {
                console.error('檢查用戶 ID 時出錯:', error);
                submitButton.innerHTML = '開始創作';
                submitButton.disabled = false;
            });
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
