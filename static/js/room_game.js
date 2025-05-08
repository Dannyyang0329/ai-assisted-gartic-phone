document.addEventListener('DOMContentLoaded', function() {
    const gameRoomDataEl = document.getElementById('game-room-data');
    const roomName = gameRoomDataEl.getAttribute('data-room-name');

    const drawingCanvasEl = document.getElementById('drawing-canvas');
    const canvasContainer = document.getElementById('canvas-container');
    
    // 動態設定畫布尺寸以匹配容器
    function resizeCanvas() {
        const cs = getComputedStyle(canvasContainer);
        const width = parseInt(cs.getPropertyValue('width'), 10);
        const height = parseInt(cs.getPropertyValue('height'), 10);
        drawingCanvasEl.width = width;
        drawingCanvasEl.height = height;
        
        // 重新繪製背景色和恢復 context 設置
        if (context) {
            context.fillStyle = "#FFFFFF";
            context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
            context.lineCap = 'round';
            context.lineJoin = 'round';
            context.lineWidth = lineWidth.value;
            context.strokeStyle = colorPicker.value;
        }
    }

    const context = drawingCanvasEl.getContext('2d');
    const clearButton = document.getElementById('clear-button');
    const colorPicker = document.getElementById('color-picker');
    const lineWidth = document.getElementById('line-width');
    const lineWidthValue = document.getElementById('line-width-value');
    
    // 獲取當前登入用戶信息 (sessionStorage)
    const user_id = sessionStorage.getItem('artflow_userid');
    if (!user_id) {
        // 如果沒有用戶ID，可以考慮重定向或顯示錯誤
        console.error("User ID not found in session storage. Redirecting to home.");
        window.location.href = '/?error=session_expired'; // 或者其他適當的處理
        return; // 停止執行後續代碼
    }
    
    // UI 元素
    const gameStatus = document.getElementById('game-status');
    const playerList = document.getElementById('players');
    const playerCountDisplay = document.getElementById('player-count-display');
    const promptInputArea = document.getElementById('prompt-input-area');
    const promptInput = document.getElementById('prompt-input');
    const submitPromptButton = document.getElementById('submit-prompt-button');
    const drawingArea = document.getElementById('drawing-area');
    const promptToDraw = document.getElementById('prompt-to-draw').querySelector('span');
    const submitDrawingButton = document.getElementById('submit-drawing-button');
    const guessInputArea = document.getElementById('guess-input-area');
    const imageToGuess = document.getElementById('image-to-guess');
    const guessInput = document.getElementById('guess-input');
    const submitGuessButton = document.getElementById('submit-guess-button');
    const resultsArea = document.getElementById('results-area');
    const booksContainer = document.getElementById('books-container');

    // 遊戲狀態變數
    let currentGameState = 'waiting';
    let myPlayerId = null;
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;

    // 初始化畫布
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.lineWidth = 5; // 初始值
    context.fillStyle = "#FFFFFF"; // 確保背景是白色
    // resizeCanvas 會處理初始繪製，或者在這裡明確調用
    // context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);


    // --- WebSocket 連接 ---
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const gameSocket = new WebSocket(
        `${wsProtocol}//${window.location.host}/ws/game/${roomName}/?userid=${encodeURIComponent(user_id)}`
    );

    gameSocket.onopen = function(e) {
        console.log('WebSocket connection established');
        // Client is ready, will wait for game_state_update or specific assignments.
        // If client is reconnecting, server might send current state.
        // For new game, client sends 'start_game' which host (or first player) triggers.
        // This 'start_game' message is a signal for the server that this client is ready
        // and if it's the host, it might trigger the actual game logic start.
        // The actual game start (prompting) is triggered by the host or server logic.
        sendMessage('start_game'); // Signal readiness and intent to start/join game flow
        showStatusMessage('正在連接到遊戲...', 'info'); 
    };
    
    gameSocket.onclose = function(e) {
        console.error('WebSocket connection closed unexpectedly');
        showStatusMessage('與伺服器的連線已中斷，請重新整理頁面。', 'error');
    };

    gameSocket.onerror = function(e) {
        console.error('WebSocket error:', e);
        showStatusMessage('連線錯誤，請檢查網路或伺服器狀態。', 'error');
    };

    gameSocket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        const messageType = data.type;
        const payload = data.payload;

        console.log("Received message:", messageType, payload);

        switch (messageType) {
            case 'game_state_update':
                myPlayerId = payload.your_player_id || myPlayerId; 
                updateUI(payload);
                break;
            case 'assign_prompt': // New: Server assigns task to submit a prompt
                showPromptInput();
                break;
            case 'request_drawing': // Existing: Server assigns task to draw
                showDrawingArea(payload.prompt_or_guess, payload.round);
                break;
            case 'request_guess': // Existing: Server assigns task to guess
                showGuessInput(payload.drawing_data, payload.round);
                break;
            case 'game_over':
                showResults(payload);
                break;
            case 'clear_canvas_instruction':
                clearLocalCanvas();
                break;
            case 'notification': // Added for server-sent notifications
                showStatusMessage(payload.message, payload.level || 'info');
                break;
            case 'error':
                showStatusMessage(`錯誤: ${payload.message}`, 'error');
                break;
            default:
                console.warn("Unhandled message type:", messageType);
        }
    };

    // --- UI 更新函數 ---
    function updateUI(stateData) {
        currentGameState = stateData.state;
        // Use a more specific status message if available, otherwise generate default
        let statusMsg = stateData.status_message || getGameStateText(currentGameState);
        if (stateData.state !== 'prompting' && stateData.state !== 'finished' && stateData.current_display_round > 0) {
             statusMsg = `第 ${stateData.current_display_round} / ${stateData.total_display_rounds} 回合 - ${getGameStateText(currentGameState)}`;
             if(stateData.status_message) statusMsg += ` (${stateData.status_message})`;
        } else if (stateData.status_message) {
            statusMsg = stateData.status_message;
        }

        showStatusMessage(statusMsg, currentGameState);
        updatePlayerList(stateData.players, stateData.waiting_on, stateData.turn_order);

        // 更新回合指示器
        const currentRoundEl = document.getElementById('current-round');
        const totalRoundsEl = document.getElementById('total-rounds');
        const roundIndicator = document.getElementById('round-indicator');

        if (currentRoundEl && totalRoundsEl && roundIndicator) {
            if (stateData.state === 'prompting' || stateData.state === 'finished' || stateData.total_display_rounds === 0) {
                roundIndicator.classList.add('hidden');
            } else {
                currentRoundEl.textContent = stateData.current_display_round || 0;
                totalRoundsEl.textContent = stateData.total_display_rounds || 0;
                roundIndicator.classList.remove('hidden');
            }
        }
        
        // 根據遊戲狀態啟用/禁用輸入
        // Prompt input area is shown/hidden by showPromptInput()
        // Drawing controls are handled by showDrawingArea()
        // Guess input area is shown/hidden by showGuessInput()

        if (stateData.state === 'prompting' && !submitPromptButton.disabled) {
            // If it's prompting state and button is enabled, it means it's this player's turn to prompt
            // (or server sent assign_prompt)
        } else if (stateData.state !== 'prompting') {
            promptInput.disabled = true;
            submitPromptButton.disabled = true;
        }
        // Other inputs (drawing, guess) are managed by their respective showXXX functions
    }

    function getGameStateText(state) {
        const texts = {
            'initializing': '遊戲初始化中...',
            'prompting': '出題階段',
            'drawing': '繪畫階段',
            'guessing': '猜測階段',
            'finished': '遊戲結束',
            'error': '發生錯誤'
        };
        return texts[state] || '未知狀態';
    }

    function showStatusMessage(message, type = 'info') {
        const statusTextEl = gameStatus.querySelector('span');
        const statusIconEl = gameStatus.querySelector('.status-icon');
        
        statusTextEl.textContent = message;
        statusIconEl.className = 'status-icon'; // Reset classes
        
        // Add type-specific class for styling icon
        if (type === 'connecting') {
            statusIconEl.classList.add('status-connecting');
        } else if (type === 'error') {
            statusIconEl.classList.add('status-error');
        } else if (currentGameState) {
             statusIconEl.classList.add(`status-${currentGameState}`);
        }
    }

    function updatePlayerList(playersData, waitingOn, turnOrder) { 
        playerList.innerHTML = ''; 
        const playerIdsInOrder = turnOrder && turnOrder.length > 0 ? turnOrder : (playersData ? Object.keys(playersData) : []);
        
        if(playerCountDisplay) {
            const totalPlayersEl = document.getElementById('player-total');
            playerCountDisplay.textContent = playerIdsInOrder.length; // Active players in turn order
            if (totalPlayersEl) {
                totalPlayersEl.textContent = playerIdsInOrder.length; 
            }
        }

        for (const playerId of playerIdsInOrder) {
            const player = playersData ? playersData[playerId] : null;
            if (!player) continue; // 防禦性程式碼

            const li = document.createElement('li');
            li.className = 'player-item';
            
            // 創建玩家狀態指示燈
            const statusDot = document.createElement('span');
            statusDot.className = 'player-status-dot';
            
            // 添加適當的類別
            if (waitingOn && waitingOn.includes(playerId)) {
                statusDot.classList.add('waiting');
            } else if (currentGameState !== 'waiting' && currentGameState !== 'finished') {
                // Consider player.status if available, otherwise assume ready if not waiting
                if (player.status === 'submitted' || player.status === 'done') { // Example statuses
                    statusDot.classList.add('ready');
                } else if (player.status === 'pending') { // Example status
                     statusDot.classList.add('waiting'); // Or a different style for 'pending'
                } else {
                    statusDot.classList.add('ready'); // Default to ready if in active game phase and not waiting
                }
            }
            
            li.appendChild(statusDot);
            
            // 添加玩家名稱
            const nameSpan = document.createElement('span');
            nameSpan.className = 'player-name';
            nameSpan.textContent = player.name || `玩家 ${playerId.substring(0, 4)}`;
            
            // 如果是機器人，添加標籤
            if (player.isBot) {
                const botTag = document.createElement('span');
                botTag.className = 'player-tag bot-tag';
                botTag.textContent = '機器人';
                nameSpan.appendChild(botTag);
            }
            
            // 如果是當前玩家，添加標籤
            if (playerId === myPlayerId) {
                const youTag = document.createElement('span');
                youTag.className = 'player-tag you-tag';
                youTag.textContent = '(你)';
                nameSpan.appendChild(youTag);
            }
            li.appendChild(nameSpan);

            // 顯示玩家是否已完成當前回合的動作 (如果後端提供此資訊)
            // 例如: if (player.action_completed) { ... }
            // 這裡我們根據 waitingOn 來判斷，如果不在 waitingOn 列表且遊戲在進行中，則視為已完成
            if (currentGameState !== 'waiting' && currentGameState !== 'finished') {
                const statusText = document.createElement('span');
                statusText.className = 'player-status';
                if (waitingOn && waitingOn.includes(playerId)) {
                    statusText.textContent = '等待中';
                } else {
                    statusText.textContent = '已完成';
                    statusText.classList.add('completed');
                }
                li.appendChild(statusText);
            }
            
            playerList.appendChild(li);
        }
    }

    function hideAllSections() {
        document.querySelectorAll('.game-stage-area').forEach(el => {
            el.classList.add('hidden');
        });
    }

    function showPromptInput() {
        hideAllSections();
        promptInputArea.classList.remove('hidden');
        promptInputArea.classList.add('fade-in-animation');
        promptInput.disabled = false;
        promptInput.value = '';
        promptInput.focus();
        submitPromptButton.disabled = false;
        showStatusMessage('請輸入你的題目', 'info');
    }

    function showDrawingArea(promptText, round) { // round is display_round
        hideAllSections();
        drawingArea.classList.remove('hidden');
        drawingArea.classList.add('fade-in-animation');
        
        resizeCanvas(); 
        promptToDraw.textContent = promptText;
        document.getElementById('prompt-to-draw').classList.remove('hidden'); // Make sure prompt is visible
        clearLocalCanvas(); 
        submitDrawingButton.disabled = false;
        showStatusMessage(`第 ${round} 回合 - 請根據提示繪畫`, 'info');
    }

    function showGuessInput(drawingDataUrl, round) { // round is display_round
        hideAllSections();
        guessInputArea.classList.remove('hidden');
        guessInputArea.classList.add('fade-in-animation');
        
        imageToGuess.src = drawingDataUrl;
        guessInput.disabled = false;
        guessInput.value = '';
        guessInput.focus();
        submitGuessButton.disabled = false;
        showStatusMessage(`第 ${round} 回合 - 請猜測這幅畫作`, 'info');
    }

    function showResults(payload) {
        hideAllSections();
        resultsArea.classList.remove('hidden');
        resultsArea.classList.add('fade-in-animation');
        
        booksContainer.innerHTML = ''; 
        
        // Use turn_order to display books consistently
        const orderedPlayerIds = payload.turn_order || Object.keys(payload.books);

        orderedPlayerIds.forEach((originalPlayerId, bookIndex) => {
            const bookData = payload.books[originalPlayerId];
            if (!bookData) return;

            const bookDiv = document.createElement('div');
            bookDiv.className = 'book';
            
            const bookTitle = document.createElement('h4');
            const initiatorName = payload.players[originalPlayerId]?.name || `玩家 ${originalPlayerId.substring(0,4)}`;
            bookTitle.textContent = `${initiatorName} 的故事本 #${bookIndex + 1}`;
            bookDiv.appendChild(bookTitle);

            const progressLine = document.createElement('div');
            progressLine.className = 'book-progress-line';
            bookDiv.appendChild(progressLine);

            bookData.forEach((item, itemIndex) => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'book-item';

                const itemPlayerId = item.player;
                const itemPlayerName = payload.players[itemPlayerId]?.name || `玩家 ${itemPlayerId.substring(0,4)}`;

                const typeTag = document.createElement('div');
                typeTag.className = 'book-item-tag';
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'book-item-content';

                // Display round number for drawing and guess
                let roundText = "";
                if (item.round > 0) { // round 0 is initial prompt
                    roundText = ` (第 ${item.round} 回合)`;
                }

                if (item.type === 'prompt') {
                    typeTag.textContent = '題目';
                    typeTag.classList.add('tag-prompt');
                    const contentText = document.createElement('p');
                    contentText.innerHTML = `<strong>${itemPlayerName}</strong> 提出了題目：<br>"${item.data}"`;
                    contentDiv.appendChild(contentText);
                } else if (item.type === 'drawing') {
                    typeTag.textContent = '繪畫';
                    typeTag.classList.add('tag-drawing');
                    
                    const contentText = document.createElement('p');
                    contentText.innerHTML = `<strong>${itemPlayerName}</strong> 根據上一個提示畫了${roundText}：`;
                    contentDiv.appendChild(contentText);
                    
                    const img = document.createElement('img');
                    img.src = item.data;
                    img.alt = `${itemPlayerName} 的繪畫`;
                    img.className = 'book-drawing';
                    contentDiv.appendChild(img);
                } else if (item.type === 'guess') {
                    typeTag.textContent = '猜測';
                    typeTag.classList.add('tag-guess');
                    const contentText = document.createElement('p');
                    contentText.innerHTML = `<strong>${itemPlayerName}</strong> 猜測這是${roundText}：<br>"${item.data}"`;
                    contentDiv.appendChild(contentText);
                }
                
                itemDiv.appendChild(typeTag);
                itemDiv.appendChild(contentDiv);
                bookDiv.appendChild(itemDiv);
            });
            booksContainer.appendChild(bookDiv);
        });
        showStatusMessage("遊戲結束！查看結果。", "finished");
    }
    
    // 分享結果功能 (保持與原HTML一致)
    window.shareResults = function() { // Make it global if called from HTML onclick
        const shareText = `我剛剛在 ArtFlow 完成了一場有趣的創意接力遊戲！來和我一起玩：${window.location.origin}`;
        
        if (navigator.share) {
            navigator.share({
                title: 'ArtFlow 遊戲結果',
                text: shareText,
                url: window.location.href, // 分享當前房間的結果頁面 (如果適用) 或首頁
            })
            .then(() => console.log('成功分享'))
            .catch((error) => console.log('分享失敗', error));
        } else {
            // 備用方案：複製到剪貼簿
            navigator.clipboard.writeText(shareText + "\n連結: " + window.location.href)
                .then(() => alert('結果連結已複製到剪貼簿！'))
                .catch(err => console.error('無法複製文字: ', err));
        }
    }

    function clearLocalCanvas() {
        context.fillStyle = "#FFFFFF"; // 確保清除後的背景是白色
        context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
    }

    clearButton.addEventListener('click', clearLocalCanvas);

    // --- 事件監聽器 ---
    function sendMessage(type, payload = {}) {
        if (gameSocket.readyState === WebSocket.OPEN) {
            gameSocket.send(JSON.stringify({ type, payload }));
        } else {
            console.error("WebSocket is not open. Cannot send message.");
            showStatusMessage("無法連接伺服器，請重新整理頁面。", "error");
        }
    }

    submitPromptButton.onclick = function() {
        const promptText = promptInput.value.trim();
        if (promptText) {
            sendMessage('submit_prompt', { prompt: promptText });
            promptInput.value = '';
            promptInput.disabled = true; // Disable after submitting
            submitPromptButton.disabled = true;
            showStatusMessage('題目已提交，等待其他玩家...', 'info'); 
        } else {
            showStatusMessage('請輸入題目！', 'error'); // 或者更友好的提示
        }
    };
    
    promptInput.onkeyup = function(e) {
        if (e.key === 'Enter') {
            submitPromptButton.click();
        }
    };

    submitDrawingButton.onclick = function() {
        const drawingDataUrl = drawingCanvasEl.toDataURL(); // 預設為 image/png
        sendMessage('submit_drawing', { drawing: drawingDataUrl });
        submitDrawingButton.disabled = true;
        showStatusMessage('繪畫已提交，等待其他玩家...', 'info'); 
    };

    submitGuessButton.onclick = function() {
        const guessText = guessInput.value.trim();
        if (guessText) {
            sendMessage('submit_guess', { guess: guessText });
            guessInput.value = '';
            submitGuessButton.disabled = true;
            showStatusMessage('猜測已提交，等待其他玩家...', 'info');
        } else {
            showStatusMessage('請輸入你的猜測！', 'error');
        }
    };
    
    guessInput.onkeyup = function(e) {
        if (e.key === 'Enter') {
            submitGuessButton.click();
        }
    };

    // --- 畫布相關 ---
    lineWidth.addEventListener('input', function() {
        lineWidthValue.textContent = this.value;
        context.lineWidth = this.value;
    });

    colorPicker.addEventListener('input', function() {
        context.strokeStyle = this.value;
    });

    // 繪圖事件
    function startDrawing(e) {
        isDrawing = true;
        const rect = drawingCanvasEl.getBoundingClientRect();
        if (e.touches) {
            [lastX, lastY] = [e.touches[0].clientX - rect.left, e.touches[0].clientY - rect.top];
        } else {
            [lastX, lastY] = [e.offsetX, e.offsetY];
        }
    }

    function draw(e) {
        if (!isDrawing) return;
        e.preventDefault(); // 防止觸控滾動頁面
        
        const rect = drawingCanvasEl.getBoundingClientRect();
        let currentX, currentY;

        if (e.touches) {
            currentX = e.touches[0].clientX - rect.left;
            currentY = e.touches[0].clientY - rect.top;
        } else {
            currentX = e.offsetX;
            currentY = e.offsetY;
        }
        
        context.beginPath();
        context.moveTo(lastX, lastY);
        context.lineTo(currentX, currentY);
        context.stroke();

        [lastX, lastY] = [currentX, currentY];
    }

    function stopDrawing() {
        isDrawing = false;
    }

    drawingCanvasEl.addEventListener('mousedown', startDrawing);
    drawingCanvasEl.addEventListener('mousemove', draw);
    drawingCanvasEl.addEventListener('mouseup', stopDrawing);
    drawingCanvasEl.addEventListener('mouseout', stopDrawing); // 當滑鼠移出畫布也停止繪畫

    drawingCanvasEl.addEventListener('touchstart', startDrawing);
    drawingCanvasEl.addEventListener('touchmove', draw);
    drawingCanvasEl.addEventListener('touchend', stopDrawing);
    drawingCanvasEl.addEventListener('touchcancel', stopDrawing);
    
    window.addEventListener('resize', resizeCanvas);

    // 初始調整畫布大小並繪製背景
    resizeCanvas(); 

    // 初始隱藏所有遊戲階段區域
    hideAllSections();
    // Initial status message will be set by gameSocket.onopen or first game_state_update
    // showStatusMessage('正在連接伺服器...', 'connecting'); 
});
