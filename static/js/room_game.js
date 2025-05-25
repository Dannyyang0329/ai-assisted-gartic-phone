document.addEventListener('DOMContentLoaded', function() {
    const gameRoomDataEl = document.getElementById('game-room-data');
    const roomName = gameRoomDataEl.getAttribute('data-room-name');

    const drawingCanvasEl = document.getElementById('drawing-canvas');
    const canvasContainer = document.getElementById('canvas-container');
    
    // 動態設定畫布尺寸以匹配容器
    function resizeCanvas() {
        const oldWidth = drawingCanvasEl.width; // 保存舊尺寸
        const oldHeight = drawingCanvasEl.height;

        const cs = getComputedStyle(canvasContainer);
        const newWidth = parseInt(cs.getPropertyValue('width'), 10);
        const newHeight = parseInt(cs.getPropertyValue('height'), 10);

        // 如果容器尚未有有效尺寸，則延遲或返回
        if (newWidth <= 0 || newHeight <= 0) {
            if (!canvasContainer.offsetParent) { // Check if container is visible
                 // console.log("Canvas container is not visible, skipping resize.");
                 return;
            }
            // 如果仍然是0，則可能是一個真正的佈局問題或初始加載問題
            if (newWidth <= 0 || newHeight <= 0) {
                console.warn(`Canvas container has zero dimensions (W: ${newWidth}, H: ${newHeight}). Resize skipped.`);
                return;
            }
        }
        
        // 僅當尺寸實際更改時才調整大小
        if (oldWidth === newWidth && oldHeight === newHeight) {
            return;
        }

        let oldImageData = null;
        // 僅當畫布具有有效尺寸時才儲存當前畫布內容
        if (oldWidth > 0 && oldHeight > 0) {
            try {
                oldImageData = context.getImageData(0, 0, oldWidth, oldHeight);
            } catch (e) {
                console.error("Error getting image data for resize: ", e);
                oldImageData = null; // 如果 getImageData 失敗，則不進行還原
            }
        }

        drawingCanvasEl.width = newWidth;
        drawingCanvasEl.height = newHeight;
        
        // --- Context 被重設：重新初始化屬性 ---

        // 1. 設定背景顏色 (這將成為畫布狀態的一部分)
        context.fillStyle = canvasBackgroundColor;
        context.fillRect(0, 0, newWidth, newHeight);

        // 2. 在新背景之上還原先前的繪圖內容 (如果有的話)
        if (oldImageData) {
            try {
                context.putImageData(oldImageData, 0, 0);
            } catch (e) {
                console.error("Error putting image data after resize: ", e);
                // 內容可能遺失，但畫布已調整大小且背景已設定。
            }
        }
        
        // 3. 重新套用持久的上下文設定 (如 lineCap/Join) 和當前工具的特定設定。
        //    呼叫 setCurrentTool 將處理 strokeStyle、lineWidth、globalCompositeOperation，
        //    以及 UI 元素，如活動按鈕和游標。
        context.lineCap = 'round'; // 這些是通用的，在 setCurrentTool 中不是工具特定的
        context.lineJoin = 'round';
        
        setCurrentTool(currentTool); // 這將為 *下一個* 繪圖操作設定上下文。
                                     // 它還確保 lineWidth 和 strokeStyle 來自 UI 控制項。
        
        // 移除原始的 clearUndoRedoStacks();
        // 保存畫布的當前狀態 (已調整大小、背景、已還原內容、準備好進行下一個工具操作)
        saveCanvasState(); 
    }

    const context = drawingCanvasEl.getContext('2d', { willReadFrequently: true }); // Added willReadFrequently
    const clearButton = document.getElementById('clear-button');
    const colorPicker = document.getElementById('color-picker');
    const lineWidth = document.getElementById('line-width');
    const lineWidthValue = document.getElementById('line-width-value');
    
    // New tool buttons
    const penToolButton = document.getElementById('pen-tool');
    const eraserToolButton = document.getElementById('eraser-tool');
    const undoButton = document.getElementById('undo-button');
    const redoButton = document.getElementById('redo-button');
    // New tool buttons from HTML
    const fillToolButton = document.getElementById('fill-tool');
    const lineToolButton = document.getElementById('line-tool');
    const rectToolButton = document.getElementById('rect-tool');
    const circleToolButton = document.getElementById('circle-tool');
    
    // Palette buttons
    const paletteColorButtons = document.querySelectorAll('.palette-color-btn');

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
    // 新增：故事書導覽按鈕和資訊
    const prevBookButton = document.getElementById('prev-book-button');
    const nextBookButton = document.getElementById('next-book-button');
    const bookPaginationInfo = document.getElementById('book-pagination-info');

    // 遊戲狀態變數
    let currentGameState = 'waiting';
    let myPlayerId = null;
    let isHostClient = false; // 新增：追蹤此客戶端是否為主持人
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    let currentTool = 'pen'; // 'pen', 'eraser', 'fill', 'line', 'rectangle', 'circle'
    let canvasBackgroundColor = "#FFFFFF"; // Default background
    let toolActiveState = { // For multi-step tools like line, rectangle, circle
        isDrawingShape: false, // Generic flag for line, rect, circle
        startX: 0,
        startY: 0,
        currentPreview: null // Stores ImageData for quick preview restore
    };
    // 新增：跟踪AI輔助次數
    let remainingAiAssists = 0;

    // Undo/Redo stacks
    let undoStack = [];
    let redoStack = [];

    // 新增：故事書顯示相關變數
    let displayedBooksOrder = [];
    let allBooksPayload = null;
    let currentBookDisplayIndex = 0;


    // 初始化畫布
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.lineWidth = 5; // 初始值
    context.fillStyle = canvasBackgroundColor; // 確保背景是白色
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
                console.log("game_state_update: myPlayerId is now:", myPlayerId); // DEBUG
                if (myPlayerId && payload.players && payload.players[myPlayerId]) {
                    const playerEntry = payload.players[myPlayerId];
                    console.log("game_state_update: Player entry for host check:", playerEntry); // DEBUG
                    console.log("game_state_update: isHost property from payload:", playerEntry.isHost); // DEBUG
                    isHostClient = playerEntry.isHost || false; // 根據 payload 更新 isHostClient
                    console.log("game_state_update: isHostClient set to:", isHostClient, "for player:", myPlayerId); // DEBUG
                } else {
                    console.warn("game_state_update: Could not determine host status. Conditions for host check not fully met."); // DEBUG
                    console.warn("game_state_update: myPlayerId:", myPlayerId, "payload.players:", payload.players); // DEBUG
                    if (payload.players && myPlayerId) {
                        console.warn("game_state_update: payload.players[myPlayerId]:", payload.players[myPlayerId]); // DEBUG
                    }
                    // isHostClient is not set to false here to allow subsequent messages to potentially set it correctly
                }
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
                showResults(payload); // showResults 內部會更新 isHostClient 並調用 updateBookNavigationButtons
                break;
            case 'update_displayed_book': // 新增：處理書本導覽更新
                if (payload && typeof payload.book_index === 'number') {
                    currentBookDisplayIndex = payload.book_index;
                    renderCurrentBook(); 
                    updateBookNavigationButtons(); // 使用已更新的 isHostClient
                }
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
            case 'ai_drawing_result':
                handleAiDrawingResult(payload);
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

        if (stateData.state === 'prompting') {
            // If it's prompting state and button is enabled, it means it's this player's turn to prompt
            // (or server sent assign_prompt)
            // Additional check: if this player is in waiting_on and is a real player, show prompt input.
            // This handles cases where the player connects slightly late.
            if (stateData.waiting_on && stateData.waiting_on.includes(myPlayerId)) {
                const myPlayerData = stateData.players ? stateData.players[myPlayerId] : null;
                if (myPlayerData && !myPlayerData.isBot) {
                   showPromptInput();
                }
            }
        } else if (stateData.state !== 'prompting') {
            promptInput.disabled = true;
            submitPromptButton.disabled = true;
            // promptInputArea.classList.add('hidden'); // This is handled by hideAllSections in showX functions
        }
        // Other inputs (drawing, guess) are managed by their respective showXXX functions

        // 更新AI輔助次數和按鈕狀態
        if (stateData.ai_assist_usage && myPlayerId) {
            const myUsage = stateData.ai_assist_usage[myPlayerId] || 0;
            const maxAllowed = stateData.max_ai_assists_allowed || 0;
            remainingAiAssists = Math.max(0, maxAllowed - myUsage);
            
            // 更新UI上的剩餘次數顯示
            const remainingAiAssistsEl = document.getElementById('remaining-ai-assists');
            if (remainingAiAssistsEl) {
                remainingAiAssistsEl.textContent = remainingAiAssists;
            }
            
            // 更新AI輔助按鈕狀態
            updateAiAssistButtonState();
        }
    }

    // 新增：更新AI輔助按鈕狀態的函數
    function updateAiAssistButtonState() {
        if (aiAssistButton) {
            if (remainingAiAssists <= 0) {
                aiAssistButton.disabled = true;
                aiAssistButton.title = "已達AI輔助次數上限";
                aiAssistButton.classList.add('disabled');
            } else {
                aiAssistButton.disabled = false;
                aiAssistButton.title = "AI輔助繪畫";
                aiAssistButton.classList.remove('disabled');
            }
        }
        
        // 同時更新modal中的提交按鈕
        if (aiAssistSubmitBtn) {
            aiAssistSubmitBtn.disabled = (remainingAiAssists <= 0);
        }
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
        
        // 確保在調用 resizeCanvas 之前，瀏覽器有機會計算 drawingArea 的新尺寸
        // requestAnimationFrame 通常用於此類情況，以確保在下一次繪製之前執行
        requestAnimationFrame(() => {
            resizeCanvas(); // 在容器可見且尺寸計算後調整畫布大小
            promptToDraw.textContent = promptText;
            document.getElementById('prompt-to-draw').classList.remove('hidden'); // Make sure prompt is visible
            clearLocalCanvas(); // 這也會保存撤銷的初始狀態
            submitDrawingButton.disabled = false;
            setCurrentTool('pen'); // 默認為畫筆工具
            lineWidth.dispatchEvent(new Event('input')); // Ensure line width is applied from current slider value
            showStatusMessage(`第 ${round} 回合 - 請根據提示繪畫`, 'info');
        });
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
        
        if (payload.your_player_id) {
            myPlayerId = payload.your_player_id;
            console.log("showResults: myPlayerId updated from game_over payload to:", myPlayerId); // DEBUG
        }
        
        allBooksPayload = payload; 
        
        console.log("showResults: Full payload received for game_over:", JSON.stringify(payload, null, 2)); // DEBUG
        console.log("showResults: myPlayerId before host check:", myPlayerId); // DEBUG

        if (myPlayerId && payload.players && typeof payload.players === 'object' && payload.players[myPlayerId]) {
            const playerEntry = payload.players[myPlayerId]; 
            console.log("showResults: Player entry for host check (payload.players[myPlayerId]):", JSON.stringify(playerEntry, null, 2)); // DEBUG
            console.log("showResults: Direct isHost property from payload (playerEntry.isHost):", playerEntry.isHost); // DEBUG

            isHostClient = playerEntry.isHost || false; // 根據 payload 更新 isHostClient
            console.log("showResults: isHostClient determined in IF branch:", isHostClient, "for player:", myPlayerId); // DEBUG
        } else {
            console.warn("showResults: Could not determine host status (ELSE branch). Conditions not met for host check."); // DEBUG
            console.warn("showResults: myPlayerId:", myPlayerId); // DEBUG
            console.warn("showResults: payload.players type:", typeof payload.players); // DEBUG
            console.warn("showResults: payload.players content:", JSON.stringify(payload.players, null, 2)); // DEBUG
            if (payload.players && myPlayerId) {
                console.warn("showResults: payload.players[myPlayerId] (if players is object):", payload.players ? payload.players[myPlayerId] : "payload.players is not an object or undefined"); // DEBUG
            }
            isHostClient = false; 
            console.log("showResults: isHostClient defaulted to false in ELSE branch."); // DEBUG
        }

        displayedBooksOrder = payload.turn_order || Object.keys(payload.books || {});

        currentBookDisplayIndex = 0; 

        if (payload.initial_book_index !== undefined) { 
            currentBookDisplayIndex = payload.initial_book_index;
        }


        if (displayedBooksOrder.length > 0) {
            renderCurrentBook();
        } else {
            booksContainer.innerHTML = '<p>沒有故事本可以顯示。</p>';
        }
        updateBookNavigationButtons(); // 調用更新按鈕狀態的函數
        
        showStatusMessage("遊戲結束！查看結果。", "finished");
    }

    function renderCurrentBook() {
        booksContainer.innerHTML = ''; // 清空現有的書本
    
        if (!allBooksPayload || displayedBooksOrder.length === 0) {
            return;
        }
    
        // 創建之前、當前和下一個故事本
        for (let i = 0; i < displayedBooksOrder.length; i++) {
            const originalPlayerId = displayedBooksOrder[i];
            const bookData = allBooksPayload.books[originalPlayerId];
            const playersData = allBooksPayload.players; // 從 payload 中獲取玩家數據
    
            if (!bookData) continue;
    
            const bookDiv = document.createElement('div');
            bookDiv.className = 'book';
            
            // 設置適當的類別用於轉場動畫
            if (i === currentBookDisplayIndex) {
                bookDiv.classList.add('active');
            } else if (i < currentBookDisplayIndex) {
                bookDiv.classList.add('previous');
            } else {
                bookDiv.classList.add('next');
            }
            
            const bookTitle = document.createElement('h4');
            const initiatorName = playersData[originalPlayerId]?.name || `玩家 ${originalPlayerId.substring(0,4)}`;
            bookTitle.textContent = `${initiatorName} 的故事本`;
            bookDiv.appendChild(bookTitle);
    
            const progressLine = document.createElement('div');
            progressLine.className = 'book-progress-line';
            bookDiv.appendChild(progressLine);
    
            bookData.forEach((item, itemIndex) => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'book-item';
                // 添加用於動畫延遲的自定義屬性
                itemDiv.style.setProperty('--item-index', itemIndex);
    
                const itemPlayerId = item.player;
                const itemPlayerName = playersData[itemPlayerId]?.name || `玩家 ${itemPlayerId.substring(0,4)}`;
    
                const typeTag = document.createElement('div');
                typeTag.className = 'book-item-tag';
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'book-item-content';
    
                let roundText = "";
                if (item.round > 0) {
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
        }
    }
    
    // 訂閱事件來處理Prev/Next導航和WebSocket消息
    function updateBookNavigationButtons() {
        if (displayedBooksOrder.length === 0) {
            prevBookButton.style.display = 'none';
            nextBookButton.style.display = 'none';
            bookPaginationInfo.style.display = 'none';
            return;
        }
    
        prevBookButton.style.display = 'inline-flex';
        nextBookButton.style.display = 'inline-flex';
        bookPaginationInfo.style.display = 'inline';
    
        console.log("[Update Nav Buttons] isHostClient:", isHostClient, "currentBookDisplayIndex:", currentBookDisplayIndex, "total books:", displayedBooksOrder.length); // DEBUG
    
        if (isHostClient) {
            prevBookButton.disabled = currentBookDisplayIndex === 0;
            nextBookButton.disabled = currentBookDisplayIndex >= displayedBooksOrder.length - 1;
        } else {
            prevBookButton.disabled = true;
            nextBookButton.disabled = true;
        }
        
        // 更新當前故事本顯示
        const allBooks = document.querySelectorAll('.book');
        allBooks.forEach((book, index) => {
            book.classList.remove('active', 'previous', 'next');
            
            if (index === currentBookDisplayIndex) {
                book.classList.add('active');
            } else if (index < currentBookDisplayIndex) {
                book.classList.add('previous');
            } else {
                book.classList.add('next');
            }
        });
        
        if (bookPaginationInfo) {
            bookPaginationInfo.textContent = `第 ${currentBookDisplayIndex + 1} / ${displayedBooksOrder.length} 本`;
        }
    }
    

    if (prevBookButton) {
        prevBookButton.addEventListener('click', () => {
            console.log("[Prev Button Click] isHostClient:", isHostClient, "currentBookDisplayIndex:", currentBookDisplayIndex); // DEBUG
            if (isHostClient && currentBookDisplayIndex > 0) {
                // 主持人點擊，發送訊息到伺服器
                console.log('[Host Action] Sending navigate_book: prev');
                sendMessage('navigate_book', { direction: 'prev' });
            } else if (!isHostClient) {
                console.log("[Prev Button Click] Not host. Button should be disabled. isHostClient:", isHostClient); // DEBUG
            } else {
                console.log("[Prev Button Click] Host, but at boundary or other condition not met. currentBookDisplayIndex:", currentBookDisplayIndex); // DEBUG
            }
        });
    }

    if (nextBookButton) {
        nextBookButton.addEventListener('click', () => {
            console.log("[Next Button Click] isHostClient:", isHostClient, "currentBookDisplayIndex:", currentBookDisplayIndex, "displayedBooksOrder.length:", displayedBooksOrder.length); // DEBUG
            if (isHostClient && currentBookDisplayIndex < displayedBooksOrder.length - 1) {
                // 主持人點擊，發送訊息到伺服器
                console.log('[Host Action] Sending navigate_book: next');
                sendMessage('navigate_book', { direction: 'next' });
            } else if (!isHostClient) {
                console.log("[Next Button Click] Not host. Button should be disabled. isHostClient:", isHostClient); // DEBUG
            } else {
                console.log("[Next Button Click] Host, but at boundary or other condition not met. currentBookDisplayIndex:", currentBookDisplayIndex, "limit:", displayedBooksOrder.length - 1); // DEBUG
            }
        });
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
        context.fillStyle = canvasBackgroundColor; // 確保清除後的背景是白色
        context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
        clearUndoRedoStacks();
        saveCanvasState(); // Save the cleared state as the first undo state
    }

    clearButton.addEventListener('click', clearLocalCanvas);

    // --- Undo/Redo Logic ---
    function saveCanvasState() {
        if (undoStack.length >= 20) { // Limit undo history
            undoStack.shift(); // Remove the oldest state
        }
        undoStack.push(drawingCanvasEl.toDataURL());
        redoStack = []; // Clear redo stack whenever a new drawing action is made
        updateUndoRedoButtons();
    }

    function clearUndoRedoStacks() {
        undoStack = [];
        redoStack = [];
        updateUndoRedoButtons();
    }
    
    function undo() {
        if (undoStack.length > 1) { 
            const currentState = undoStack.pop();
            redoStack.push(currentState);
            const prevStateDataUrl = undoStack[undoStack.length - 1]; 
            const img = new Image();
            img.onload = function() {
                // 清除前確保畫布尺寸是正確的 (通常在 resizeCanvas 中處理)
                context.clearRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height); 
                context.fillStyle = canvasBackgroundColor;
                context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
                context.drawImage(img, 0, 0);
            };
            img.onerror = function() {
                console.error("Error loading image for undo.");
                // Handle error, maybe try to pop again or disable undo
            }
            img.src = prevStateDataUrl;
        }
        updateUndoRedoButtons();
    }

    function redo() {
        if (redoStack.length > 0) {
            const nextStateDataUrl = redoStack.pop();
            undoStack.push(nextStateDataUrl);
            const img = new Image();
            img.onload = function() {
                context.clearRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height); 
                context.fillStyle = canvasBackgroundColor;
                context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
                context.drawImage(img, 0, 0);
            };
            img.onerror = function() {
                console.error("Error loading image for redo.");
            }
            img.src = nextStateDataUrl;
        }
        updateUndoRedoButtons();
    }

    function updateUndoRedoButtons() {
        undoButton.disabled = undoStack.length <= 1; // Disabled if only initial state or no states
        redoButton.disabled = redoStack.length === 0;
    }

    undoButton.addEventListener('click', undo);
    redoButton.addEventListener('click', redo);


    // --- Tool Selection Logic ---
    function setCurrentTool(tool) {
        currentTool = tool;
        // Reset active state for all buttons first
        [penToolButton, eraserToolButton, fillToolButton, lineToolButton, rectToolButton, circleToolButton].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });
        drawingCanvasEl.className = ''; // Reset cursor classes

        toolActiveState.isDrawingShape = false; // Reset shape drawing state when changing tools

        switch (tool) {
            case 'pen':
                if (penToolButton) penToolButton.classList.add('active');
                drawingCanvasEl.classList.add('crosshair'); 
                context.strokeStyle = colorPicker.value; // Ensure color is set
                context.lineWidth = lineWidth.value;
                context.globalCompositeOperation = 'source-over';
                updateLineWidthGradient(colorPicker.value); // 更新漸層顏色
                break;
            case 'eraser':
                if (eraserToolButton) eraserToolButton.classList.add('active');
                drawingCanvasEl.classList.add('eraser-cursor');
                context.lineWidth = lineWidth.value; 
                context.globalCompositeOperation = 'destination-out';
                break;
            case 'fill':
                if (fillToolButton) fillToolButton.classList.add('active');
                drawingCanvasEl.classList.add('fill-cursor');
                // Fill color is taken directly from colorPicker.value in floodFill
                context.globalCompositeOperation = 'source-over'; // Reset for safety, though fill doesn't use it
                break;
            case 'line':
                if (lineToolButton) lineToolButton.classList.add('active');
                drawingCanvasEl.classList.add('line-cursor');
                context.strokeStyle = colorPicker.value;
                context.lineWidth = lineWidth.value;
                context.globalCompositeOperation = 'source-over';
                break;
            case 'rectangle':
                if (rectToolButton) rectToolButton.classList.add('active');
                drawingCanvasEl.classList.add('rect-cursor');
                context.strokeStyle = colorPicker.value;
                context.lineWidth = lineWidth.value;
                context.globalCompositeOperation = 'source-over';
                break;
            case 'circle':
                if (circleToolButton) circleToolButton.classList.add('active');
                drawingCanvasEl.classList.add('circle-cursor');
                context.strokeStyle = colorPicker.value;
                context.lineWidth = lineWidth.value;
                context.globalCompositeOperation = 'source-over';
                break;
        }
    }

    if (penToolButton) penToolButton.addEventListener('click', () => setCurrentTool('pen'));
    if (eraserToolButton) eraserToolButton.addEventListener('click', () => setCurrentTool('eraser'));
    if (fillToolButton) fillToolButton.addEventListener('click', () => setCurrentTool('fill'));
    if (lineToolButton) lineToolButton.addEventListener('click', () => setCurrentTool('line'));
    if (rectToolButton) rectToolButton.addEventListener('click', () => setCurrentTool('rectangle'));
    if (circleToolButton) circleToolButton.addEventListener('click', () => setCurrentTool('circle'));

    // Palette color button listeners
    paletteColorButtons.forEach(button => {
        button.addEventListener('click', function() {
            const selectedColor = this.dataset.color;
            colorPicker.value = selectedColor;
            
            // Trigger input event on colorPicker to update context.strokeStyle and other dependent logic
            colorPicker.dispatchEvent(new Event('input'));

            // Update selected state for palette buttons
            paletteColorButtons.forEach(btn => btn.classList.remove('selected'));
            this.classList.add('selected');
            
            // 不需要手動調用 updateLineWidthGradient，因為已經觸發了 colorPicker 的 input 事件
        });
    });

    // 新增一個函數來更新線寬控制器漸層顏色
    function updateLineWidthGradient(color) {
        // 從淺灰色到所選顏色的漸層
        lineWidth.style.background = `linear-gradient(to right, #e0e0e0, ${color})`;
    }

    // 修改 colorPicker 事件監聽器
    colorPicker.addEventListener('input', function() {
        if (currentTool === 'pen' || currentTool === 'line' || currentTool === 'rectangle' || currentTool === 'circle') {
            context.strokeStyle = this.value;
        }
        // For fill tool, color is read directly in floodFill.
        // For eraser, strokeStyle is not used.

        // Remove 'selected' class from all palette buttons when custom color picker is used
        paletteColorButtons.forEach(btn => {
            if (btn.dataset.color.toLowerCase() === this.value.toLowerCase()) {
                btn.classList.add('selected');
            } else {
                btn.classList.remove('selected');
            }
        });
        
        // 更新線寬控制器的漸層顏色
        updateLineWidthGradient(this.value);
    });

    // 在初始化時設置線寬控制器的漸層顏色
    window.addEventListener('DOMContentLoaded', function() {
        // 使用初始顏色值更新漸層
        updateLineWidthGradient(colorPicker.value);
    });

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

    // 新增 AI 輔助按鈕與 modal 元素引用
    const aiAssistButton = document.getElementById('ai-assist-button');
    const aiAssistModal = document.getElementById('ai-assist-modal');
    const aiAssistModalClose = document.getElementById('ai-assist-modal-close');
    const aiAssistCancelBtn = document.getElementById('ai-assist-cancel-btn');
    const aiAssistSubmitBtn = document.getElementById('ai-assist-submit-btn');
    const aiAssistPrompt = document.getElementById('ai-assist-prompt');
    
    // 顯示 AI 輔助 Modal
    function showAiAssistModal() {
        if (aiAssistModal) {
            aiAssistModal.classList.remove('hidden');
            setTimeout(() => {
                aiAssistModal.classList.add('active');
                if (aiAssistPrompt) {
                    aiAssistPrompt.focus();
                }
            }, 10);
            document.body.style.overflow = 'hidden'; // 防止背景滾动
        }
    }

    // 隱藏 AI 輔助 Modal
    function hideAiAssistModal() {
        if (aiAssistModal) {
            aiAssistModal.classList.remove('active');
            setTimeout(() => {
                aiAssistModal.classList.add('hidden');
                document.body.style.overflow = ''; // 恢復背景滾动
            }, 300); // 等待動畫完成
        }
    }

    // 綁定 AI 輔助按鈕點擊事件
    if (aiAssistButton) {
        aiAssistButton.onclick = function() {
            if (remainingAiAssists > 0) {
                showAiAssistModal();
            } else {
                showStatusMessage('已達AI輔助次數上限', 'error');
            }
        };
    }

    // 關閉 Modal 的點擊事件
    if (aiAssistModalClose) {
        aiAssistModalClose.onclick = hideAiAssistModal;
    }

    // 取消按鈕點擊事件
    if (aiAssistCancelBtn) {
        aiAssistCancelBtn.onclick = hideAiAssistModal;
    }

    // Modal 背景點擊關閉
    if (aiAssistModal) {
        aiAssistModal.addEventListener('click', function(e) {
            if (e.target === aiAssistModal) {
                hideAiAssistModal();
            }
        });
    }

    // AI 輔助繪畫生成處理
    if (aiAssistSubmitBtn) {
        aiAssistSubmitBtn.onclick = function() {
            const promptText = aiAssistPrompt.value.trim();
            if (!promptText) {
                showStatusMessage('請輸入描述內容', 'error');
                return;
            }

            // 顯示處理中狀態
            aiAssistSubmitBtn.disabled = true;
            aiAssistSubmitBtn.innerHTML = '<span class="btn-icon">⏳</span><span class="btn-text">處理中...</span>';

            // 取得當前畫布內容
            const drawingDataUrl = drawingCanvasEl.toDataURL('image/png');
            
            // 向後端發送 AI 輔助繪畫請求
            sendMessage('ai_assist_drawing', { 
                prompt: promptText,
                drawing: drawingDataUrl
            });

            // 顯示處理中訊息
            showStatusMessage('AI 正在處理您的繪畫...', 'info');
        };
    }

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
        if (currentTool === 'pen' || currentTool === 'line' || currentTool === 'rectangle' || currentTool === 'circle') {
            context.strokeStyle = this.value;
        }
        // For fill tool, color is read directly in floodFill.
        // For eraser, strokeStyle is not used.

        // Remove 'selected' class from all palette buttons when custom color picker is used
        paletteColorButtons.forEach(btn => {
            if (btn.dataset.color.toLowerCase() === this.value.toLowerCase()) {
                btn.classList.add('selected');
            } else {
                btn.classList.remove('selected');
            }
        });
        
        // 更新線寬控制器的漸層顏色
        updateLineWidthGradient(this.value);
    });

    // 繪圖事件
    function startDrawing(e) {
        if (currentTool === 'fill') return; // Fill is handled by click

        isDrawing = true;
        const rect = drawingCanvasEl.getBoundingClientRect();
        const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
        const y = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;

        lastX = x; // Still useful for pen/eraser if they use it directly
        lastY = y;

        // Apply current tool's properties before starting any path or getting image data
        setCurrentTool(currentTool); 

        if (currentTool === 'pen' || currentTool === 'eraser') {
            context.beginPath();
            context.moveTo(x, y); // Use current x, y for moveTo
        } else if (currentTool === 'line' || currentTool === 'rectangle' || currentTool === 'circle') {
            toolActiveState.isDrawingShape = true;
            toolActiveState.startX = x;
            toolActiveState.startY = y;
            if (drawingCanvasEl.width > 0 && drawingCanvasEl.height > 0) { // Ensure canvas has dimensions
                toolActiveState.currentPreview = context.getImageData(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
            } else {
                toolActiveState.currentPreview = null; // Cannot get image data if canvas is 0x0
            }
        }
    }

    function draw(e) {
        if (!isDrawing || currentTool === 'fill') return;
        e.preventDefault(); 
        
        const rect = drawingCanvasEl.getBoundingClientRect();
        const currentX = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
        const currentY = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;

        if (currentTool === 'pen' || currentTool === 'eraser') {
            context.lineTo(currentX, currentY);
            context.stroke();
            // Update lastX, lastY for continuous drawing with pen/eraser
            lastX = currentX; 
            lastY = currentY;
        } else if (toolActiveState.isDrawingShape) {
            // Restore canvas to state before last preview
            if (toolActiveState.currentPreview) {
                context.putImageData(toolActiveState.currentPreview, 0, 0);
            }
            context.beginPath();
            if (currentTool === 'line') {
                context.moveTo(toolActiveState.startX, toolActiveState.startY);
                context.lineTo(currentX, currentY);
            } else if (currentTool === 'rectangle') {
                context.rect(toolActiveState.startX, toolActiveState.startY, currentX - toolActiveState.startX, currentY - toolActiveState.startY);
            } else if (currentTool === 'circle') {
                const radius = Math.sqrt(Math.pow(currentX - toolActiveState.startX, 2) + Math.pow(currentY - toolActiveState.startY, 2));
                context.arc(toolActiveState.startX, toolActiveState.startY, radius, 0, Math.PI * 2);
            }
            context.stroke();
        }
    }

    function stopDrawing(e) {
        if (!isDrawing || currentTool === 'fill') {
            isDrawing = false; // Ensure isDrawing is reset if fill tool was active but drag occurred
            return;
        }
        
        const rect = drawingCanvasEl.getBoundingClientRect();
        let currentX, currentY;

        if (e.type === 'mouseout' && toolActiveState.isDrawingShape) {
            // For mouseout, use the last known coordinates from the 'draw' event if available,
            // or the event's coordinates if it's the only reliable source.
            // However, the event's coordinates for mouseout are where it left the canvas.
            currentX = e.offsetX; //offsetX/Y are relative to the target element
            currentY = e.offsetY;

        } else if (e.changedTouches && e.changedTouches.length > 0) {
            currentX = e.changedTouches[0].clientX - rect.left;
            currentY = e.changedTouches[0].clientY - rect.top;
        } else {
            currentX = e.clientX - rect.left;
            currentY = e.clientY - rect.top;
        }


        if (currentTool === 'pen' || currentTool === 'eraser') {
            context.closePath();
        } else if (toolActiveState.isDrawingShape) {
            if (toolActiveState.currentPreview) {
                context.putImageData(toolActiveState.currentPreview, 0, 0);
            }
            context.beginPath();
             if (currentTool === 'line') {
                context.moveTo(toolActiveState.startX, toolActiveState.startY);
                context.lineTo(currentX, currentY);
            } else if (currentTool === 'rectangle') {
                context.rect(toolActiveState.startX, toolActiveState.startY, currentX - toolActiveState.startX, currentY - toolActiveState.startY);
            } else if (currentTool === 'circle') {
                const dx = currentX - toolActiveState.startX;
                const dy = currentY - toolActiveState.startY;
                const radius = Math.sqrt(dx * dx + dy * dy);
                if (radius > 0) { // Only draw if radius is positive
                    context.arc(toolActiveState.startX, toolActiveState.startY, radius, 0, Math.PI * 2);
                }
            }
            if (currentTool === 'line' || currentTool === 'rectangle' || currentTool === 'circle') {
                 // Ensure strokeStyle and lineWidth are correctly set from current selections
                context.strokeStyle = colorPicker.value;
                context.lineWidth = lineWidth.value;
                context.stroke();
            }
            context.closePath();
            toolActiveState.isDrawingShape = false;
            toolActiveState.currentPreview = null;
        }
        
        isDrawing = false;
        if (drawingCanvasEl.width > 0 && drawingCanvasEl.height > 0) { // Only save state if canvas is valid
             saveCanvasState(); 
        }
    }

    // Flood Fill Implementation (simplified)
    function floodFill(startX, startY, fillColor) {
        const imageData = context.getImageData(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
        const data = imageData.data;
        const canvasWidth = drawingCanvasEl.width;
        const canvasHeight = drawingCanvasEl.height;

        const startIdx = (startY * canvasWidth + startX) * 4;
        const startR = data[startIdx];
        const startG = data[startIdx + 1];
        const startB = data[startIdx + 2];
        // const startA = data[startIdx + 3]; // Alpha not always needed for comparison if background is opaque

        // If start color is same as fill color, do nothing
        const fillR = parseInt(fillColor.slice(1, 3), 16);
        const fillG = parseInt(fillColor.slice(3, 5), 16);
        const fillB = parseInt(fillColor.slice(5, 7), 16);

        if (startR === fillR && startG === fillG && startB === fillB) {
            return;
        }

        const queue = [[startX, startY]];
        
        function getColor(x, y) {
            if (x < 0 || x >= canvasWidth || y < 0 || y >= canvasHeight) return [-1,-1,-1,-1]; // Out of bounds
            const idx = (y * canvasWidth + x) * 4;
            return [data[idx], data[idx+1], data[idx+2], data[idx+3]];
        }

        function setColor(x, y, r, g, b, a = 255) {
            const idx = (y * canvasWidth + x) * 4;
            data[idx] = r;
            data[idx+1] = g;
            data[idx+2] = b;
            data[idx+3] = a;
        }

        while (queue.length > 0) {
            const [x, y] = queue.shift();
            const currentColor = getColor(x,y);

            if (currentColor[0] === startR && currentColor[1] === startG && currentColor[2] === startB) {
                setColor(x, y, fillR, fillG, fillB);

                if (x + 1 < canvasWidth) queue.push([x + 1, y]);
                if (x - 1 >= 0) queue.push([x - 1, y]);
                if (y + 1 < canvasHeight) queue.push([x, y + 1]);
                if (y - 1 >= 0) queue.push([x, y - 1]);
            }
        }
        context.putImageData(imageData, 0, 0);
        saveCanvasState();
    }

    drawingCanvasEl.addEventListener('click', function(e) {
        if (currentTool === 'fill') {
            if (isDrawing) return; // Don't fill if a drag operation was mistakenly started
            const rect = drawingCanvasEl.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            floodFill(Math.floor(x), Math.floor(y), colorPicker.value);
        }
    });


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
    saveCanvasState(); // Save initial blank state for undo
    updateUndoRedoButtons(); // Initialize button states

    // 初始隱藏所有遊戲階段區域
    hideAllSections();
    // Initial status message will be set by gameSocket.onopen or first game_state_update
    // showStatusMessage('正在連接伺服器...', 'connecting'); 

    // 隱藏 AI 輔助 Modal 的全局函數
    function hideAiAssistModal() {
        if (aiAssistModal) {
            aiAssistModal.classList.remove('active');
            setTimeout(() => {
                aiAssistModal.classList.add('hidden');
                document.body.style.overflow = ''; // 恢復背景滾動
            }, 300); // 等待動畫完成
        }
    }

    // 添加處理 AI 繪畫結果的函數
    function handleAiDrawingResult(payload) {
        if (payload.success) {
            const context = drawingCanvasEl.getContext('2d');

            // 將結果圖像應用到畫布
            const img = new Image();
            img.onload = function() {
                // 清除當前畫布內容
                context.clearRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
                context.fillStyle = canvasBackgroundColor; // 使用 canvasBackgroundColor 變數
                context.fillRect(0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
                // 繪製新圖像
                context.drawImage(img, 0, 0, drawingCanvasEl.width, drawingCanvasEl.height);
                // 保存到撤銷堆疊
                saveCanvasState();
                showStatusMessage('AI 輔助繪畫已套用！', 'success');
            };
            img.onerror = function() {
                console.error("AI 繪畫圖像載入失敗");
                showStatusMessage('圖像載入失敗，請重試', 'error');
            };
            img.src = payload.image;
        } else {
            showStatusMessage(payload.error || 'AI 輔助繪畫處理失敗，請重試', 'error');
        }

        // 更新剩餘次數
        if (typeof payload.remaining_ai_assists === 'number') {
            remainingAiAssists = payload.remaining_ai_assists;
            const remainingAiAssistsEl = document.getElementById('remaining-ai-assists');
            if (remainingAiAssistsEl) {
                remainingAiAssistsEl.textContent = remainingAiAssists;
            }
            
            // 更新按鈕狀態
            updateAiAssistButtonState();
        }

        // 無論成功或失敗，都關閉 modal 並重設按鈕
        hideAiAssistModal();
        if (aiAssistSubmitBtn) {
            aiAssistSubmitBtn.disabled = remainingAiAssists <= 0;
            aiAssistSubmitBtn.innerHTML = '<span class="btn-icon">✨</span><span class="btn-text">生成繪畫</span>';
            aiAssistPrompt.value = ''; // 清空輸入框
        }
    }
});

