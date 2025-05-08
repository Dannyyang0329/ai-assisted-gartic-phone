document.addEventListener('DOMContentLoaded', function() {
    // 獲取頁面參數
    const roomName = document.getElementById('room-data').getAttribute('data-room-name');
    const csrfToken = document.getElementById('room-data').getAttribute('data-csrf-token');
    
    // 從sessionStorage獲取當前登入用戶信息artflow_userid
    const user_id = sessionStorage.getItem('artflow_userid') || null;
    if (!user_id) {
        // 如果沒有用戶ID，重定向到首頁
        window.location.href = '/?redirect_room=' + roomName;
    } else {
        // 使用fetch API將用戶ID發送到後端
        fetch('/game/register-user-id/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                userid: user_id,
                room_name: roomName
            })
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                // 如果ID註冊失敗，重定向回首頁
                window.location.href = '/?redirect_room=' + roomName + '&error=userid_taken';
            }
        })
        .catch(error => {
            console.error('註冊用戶ID時出錯:', error);
            window.location.href = '/?redirect_room=' + roomName + '&error=server_error';
        });
    }

    // DOM 元素
    const playerList = document.getElementById('player-list');
    const playerCountDisplay = document.getElementById('player-count-display');
    const chatLog = document.getElementById('chat-log');
    const chatMessageInput = document.getElementById('chat-message-input');
    const chatMessageSubmit = document.getElementById('chat-message-submit');
    const startGameButton = document.getElementById('start-game-button');
    const addBotButton = document.getElementById('add-bot');
    const removeBotButton = document.getElementById('remove-bot');
    const roomLinkInput = document.getElementById('room-link');
    const copyLinkButton = document.getElementById('copy-link');
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notification-text');

    // 玩家資料
    let players = [];
    let botCount = 0;
    const MAX_PLAYERS = 8;
    const MIN_PLAYERS_TO_START = 4;

    // 模擬初始玩家狀態（第一個玩家就是當前用戶）
    const initialPlayers = [
        {
            id: user_id,
            name: user_id,
            isHost: true,
            isBot: false
        }
    ];
    players = initialPlayers;
    updatePlayerList();
    
    // WebSocket 連接
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const gameSocket = new WebSocket(
        `${wsProtocol}//${window.location.host}/ws/waiting_room/${roomName}/?userid=${encodeURIComponent(user_id)}`
    );
    gameSocket.onopen = function(e) {
        console.log('WebSocket connection established');
    };
    gameSocket.onclose = function(e) {
        console.error('WebSocket connection closed unexpectedly');
        showNotification('連線已中斷，請重新整理頁面。', 'error');
    };
    gameSocket.onerror = function(e) {
        console.error('WebSocket error:', e);
        showNotification('連線錯誤，請檢查網路或伺服器狀態。', 'error');
    }
    gameSocket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        const messageType = data.type;
        const payload = data.payload;
        
        console.log("Received message:", messageType, payload);

        switch (messageType) {
            case 'room_update':
                updateRoomState(payload);
                break;
            case 'chat':
                appendChatMessage(payload.sender, payload.text);
                break;
            case 'notification':
                showNotification(payload.message, payload.level || 'info');
                break;
            case 'game_started':
                window.location.href = `/room/${roomName}`;
                break;
            case 'error':
                showNotification(`錯誤: ${payload.message}`, 'error');
                break;
        }
    };

    // 發送訊息到伺服器
    function sendMessage(type, payload = {}) {
        if (gameSocket.readyState === WebSocket.OPEN) {
            gameSocket.send(JSON.stringify({ type, payload }));
        } else {
            showNotification("無法連接伺服器，請重新整理頁面。", "error");
        }
    }

    // 更新房間狀態
    function updateRoomState(roomState) {
        players = roomState.players || [];
        botCount = roomState.bot_count || 0;
        
        // 更新玩家列表
        updatePlayerList();
        
        // 更新玩家數量
        const playerCount = players.length;
        playerCountDisplay.textContent = playerCount;
        
        // 更新按鈕狀態
        startGameButton.disabled = playerCount < MIN_PLAYERS_TO_START;
        addBotButton.disabled = playerCount >= MAX_PLAYERS || botCount >= 3;
        removeBotButton.disabled = botCount <= 0;
        
        // 如果有足夠玩家，顯示可以開始的提示
        if (playerCount >= MIN_PLAYERS_TO_START && startGameButton.disabled) {
            showNotification("已有足夠玩家，可以開始遊戲！", "success");
            startGameButton.disabled = false;
        }
    }

    // 更新玩家列表
    function updatePlayerList() {
        playerList.innerHTML = '';
        
        players.forEach((player, index) => {
            const li = document.createElement('li');
            li.className = 'player-item';
            
            // 創建玩家狀態指示燈
            const statusDot = document.createElement('span');
            statusDot.className = 'player-status-dot';
            
            if (player.isBot) {
                statusDot.classList.add('bot');
            } else {
                statusDot.classList.add('ready');
            }
            
            li.appendChild(statusDot);
            
            // 添加玩家順序號碼
            const orderNumber = document.createElement('span');
            orderNumber.className = 'player-number';
            orderNumber.textContent = index + 1;
            li.appendChild(orderNumber);
            
            // 添加玩家名稱
            const nameSpan = document.createElement('span');
            nameSpan.className = 'player-name';
            nameSpan.textContent = player.name;
            
            if (player.isBot) {
                nameSpan.innerHTML += ' <span class="bot-tag">機器人</span>';
            } else if (player.isHost) {
                nameSpan.innerHTML += ' <span class="host-tag">房主</span>';
            } else if (player.id === user_id) {
                nameSpan.innerHTML += ' <span class="you-tag">(你)</span>';
            }
            
            li.appendChild(nameSpan);
            
            playerList.appendChild(li);
        });
    }

    // 添加聊天訊息
    function appendChatMessage(sender, text) {
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message animate__animated animate__fadeIn';
        
        const senderElement = document.createElement('div');
        senderElement.className = 'chat-sender';
        senderElement.textContent = sender;
        
        const textElement = document.createElement('div');
        textElement.className = 'chat-text';
        textElement.textContent = text;
        
        messageElement.appendChild(senderElement);
        messageElement.appendChild(textElement);
        
        chatLog.appendChild(messageElement);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    // 顯示通知
    function showNotification(message, type = 'info') {
        notificationText.textContent = message;
        notification.className = `notification notification-${type} animate__animated animate__fadeIn`;
        notification.classList.remove('hidden');
        
        // 2秒後隱藏
        setTimeout(() => {
            notification.classList.add('animate__fadeOut');
            setTimeout(() => {
                notification.classList.add('hidden');
                notification.classList.remove('animate__fadeOut');
            }, 500);
        }, 2000);
    }

    // 添加機器人
    addBotButton.addEventListener('click', function() {
        sendMessage('add_bot');
    });

    // 移除機器人
    removeBotButton.addEventListener('click', function() {
        sendMessage('remove_bot');
    });

    // 開始遊戲
    startGameButton.addEventListener('click', function() {
        if (players.length >= MIN_PLAYERS_TO_START) {
            sendMessage('start_game');
            startGameButton.disabled = true;
            startGameButton.innerHTML = '正在準備遊戲...';
            showNotification('遊戲即將開始！', 'success');
        } else {
            showNotification(`至少需要 ${MIN_PLAYERS_TO_START} 位玩家才能開始遊戲`, 'error');
        }
    });

    // 複製連結
    copyLinkButton.addEventListener('click', function() {
        roomLinkInput.select();
        document.execCommand('copy');
        showNotification('房間連結已複製到剪貼簿！', 'success');
    });

    // 聊天功能
    chatMessageSubmit.addEventListener('click', function() {
        const message = chatMessageInput.value.trim();
        if (message) {
            sendMessage('chat_message', { message: message });
            chatMessageInput.value = '';
        }
    });
    chatMessageInput.addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            chatMessageSubmit.click();
        }
    });
    
    // 遊戲說明模態框控制
    const instructionsModal = document.getElementById('instructions-modal');
    const helpButton = document.getElementById('help-button');
    const closeModal = document.getElementById('close-modal');
    helpButton.addEventListener('click', function() {
        instructionsModal.classList.add('show');
    });
    closeModal.addEventListener('click', function() {
        instructionsModal.classList.remove('show');
    });
    // 點擊模態框外部關閉
    window.addEventListener('click', function(event) {
        if (event.target == instructionsModal) {
            instructionsModal.classList.remove('show');
        }
    });
});
