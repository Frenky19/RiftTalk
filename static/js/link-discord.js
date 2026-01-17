        // ==========================================================
        // i18n + Theme (RU/EN + Light/Dark)
        // ==========================================================
        const I18N = {
            en: {
                page_title: "Discord Account Linking",
                page_subtitle: "Link your Discord account with League of Legends for automatic voice channel connection during matches",
                current_user: "Current User",

                label_language: "Language",
                toggle_theme: "Theme",

                btn_oauth_link: "Link via Discord (recommended)",
                
                btn_donate: "Support the project",
                oauth_info: "This will securely link your account.",
                manual_discord_id_advanced: " Enter manual Discord ID (advanced)",
                manual_discord_id_link: "Manual Discord ID Link",
                label_discord_link: "Discord linking:",
                label_discord_id: "Your Discord ID:",
                ph_discord_user_id: "Enter your Discord User ID (numbers only)",
                btn_save_discord_id: "Save Discord ID",
                discord_id_needed: "Discord ID is needed to grant access to your team's voice channel. Your ID will be stored securely.",
                linked_discord_account: "Linked Discord Account:",

                match_status: "Match Status",
                btn_refresh: "Refresh",

                lbl_game_phase: "Game Phase",
                lbl_summoner: "Summoner Name",
                lbl_team: "Team",
                lbl_connected: "Connected",

                your_team_voice_channel: "Your Team's Voice Channel",
                lbl_channel_name: "Channel Name",
                lbl_status: "Status",
                btn_join_voice: "Join Voice Chat",
                btn_copy_link: "Copy Link",

                how_it_works: "How It Works",
                need_help: "Need Help?",
                support_troubleshooting: "Support & Troubleshooting",

                enable_dev_mode: "Enable Discord Developer Mode",
                copy_user_id: "Copy Your Discord User ID",
                troubleshooting: "Troubleshooting",
                troubleshoot_intro: "If you encounter issues, try these steps:",
                troubleshoot_bot_perms: "Make sure Discord bot is online and has permissions",
                troubleshoot_id_correct: "Check that your Discord ID is correct (numbers only)",
                troubleshoot_waiting_room: "Ensure you are in the Waiting Room voice channel on Discord",

                keep_open_note: "Keep this page open while playing League of Legends. The app will automatically update when match starts.",

                // Dynamic UI messages
                msg_copied: "Invite link copied to clipboard!",
                msg_copy_failed: "Couldn't copy the link. Please copy it manually.",
                msg_opening_discord: "Opening Discord invite...",
                msg_oauth_open: "Opening Discord authorization...",
                msg_invalid_id: "Enter a valid Discord User ID (digits only).",
                msg_saved: "Discord ID saved.",
                                msg_save_failed: "Couldn't save Discord ID. Please try again.",

                // Additional UI text used on this page
                doc_title: "Link Discord Account - LoL Voice Chat",
                card_discord_linking: "Discord Account Linking",
                btn_change_discord_id: "Change Discord ID",
                loading_linking: "Linking account...",
                btn_link_manual: "Link Discord Account (manual)",
                btn_refresh_status: "Refresh Status",
                voice_channel_prompt: "The match has started! Join your team's voice channel:",
                help_instructions: "Help & Instructions",
                how_to_find_discord_id: "How to find Discord ID?",
                find_discord_id_steps: "Open Discord → Settings → Advanced → Enable \"Developer Mode\" → Right-click on your avatar → \"Copy User ID\"",
                join_our_server: "Join our server",
                make_sure_in_server: "Make sure you're in",
                our_discord_server: "Our Discord server",
                important_to_know: "Important to know:",
                note_change_id: "If you need to re-link Discord, click the \"Change\" button",
                note_channels_created: "Voice channels are created automatically after the match starts",
                note_auto_connected: "You will be automatically connected to your team's channel",
                step_1: "Link account",
                step_2: "Launch League of Legends and join games",
                step_3: "When the match starts, status updates automatically",
                step_4: "Join your team's voice channel!",
                lbl_channel: "Channel:",
                lbl_team_label: "Team:",
                lbl_match: "Match:",
                lbl_player: "Player",
                lbl_id: "ID",
                lbl_saved: "Saved",
                btn_account_linked: "Account linked",
                msg_enter_new_id: "Enter new Discord ID",
                msg_match_status_error: "Could not check match status. Make sure League of Legends is running.",
                msg_match_started_ready: "✅ Match started! Your voice channel is ready.",
                msg_match_loading: "🔄 Match is loading... Voice channel will be available after match starts.",
                msg_champ_select: "🎯 Champion selection... Voice channel will be created after match starts.",
                msg_match_found_not_started: "⏳ Match found, but not started yet. Voice channel will be available after match starts.",
                msg_no_active_match: "❌ No active match found. Launch League of Legends and join a game.",
                msg_voice_ready: "🎉 Match started! Your team's voice channel is ready. Join now!",
                msg_already_linked: "✅ Discord account already linked: {id}",
                msg_oauth_linked: "✅ Discord linked via OAuth: {id}",
                server_user_found: "✅ User found on server",
                server_user_not_found: "❌ User not found on server",
                server_join_server: "Join server",
                server_join_bot_server: "Please join the bot's Discord server.",
                server_status_unknown: "⚠️ Could not check status",
                msg_auth_failed: "Could not authenticate. Launch League of Legends and try again.",
                msg_oauth_timeout: "⏳ OAuth window was opened, but linking was not detected yet. If you finished authorization, click \"Refresh Status\".",
                msg_oauth_start_failed: "Failed to start Discord OAuth.",
                msg_oauth_no_url: "No authorization URL returned.",
                msg_match_status_updated: "🔄 Match status updated",
                msg_copied_short: "Copied!"
            },
            ru: {
                page_title: "Привязка Discord",
                page_subtitle: "Привяжите Discord к League of Legends, чтобы приложение автоматически подключало вас к голосовому каналу во время матчей",
                current_user: "Текущий пользователь",

                label_language: "Язык",
                toggle_theme: "Тема",

                btn_oauth_link: "Привязать через Discord (рекомендуется)",
                
                btn_donate: "Поддержать проект",
                oauth_info: "Аккаунт будет безопасно привязан через авторизацию.",
                manual_discord_id_advanced: "Ввести Discord ID вручную",
                manual_discord_id_link: "Привязка по Discord ID вручную",
                label_discord_link: "Привязка Discord:",
                label_discord_id: "Ваш Discord ID:",
                ph_discord_user_id: "Введите User ID Discord (только цифры)",
                btn_save_discord_id: "Сохранить Discord ID",
                discord_id_needed: "Discord ID нужен, чтобы выдать доступ к голосовому каналу вашей команды. ID будет храниться безопасно.",
                linked_discord_account: "Привязанный аккаунт Discord:",

                match_status: "Статус матча",
                btn_refresh: "Обновить",

                lbl_game_phase: "Фаза игры",
                lbl_summoner: "Ник в LoL",
                lbl_team: "Команда",
                lbl_connected: "Подключено",

                your_team_voice_channel: "Голосовой канал вашей команды",
                lbl_channel_name: "Название канала",
                lbl_status: "Статус",
                btn_join_voice: "Зайти в голосовой чат",
                btn_copy_link: "Скопировать ссылку",

                how_it_works: "Как это работает",
                need_help: "Нужна помощь?",
                support_troubleshooting: "Поддержка и диагностика",

                enable_dev_mode: "Включите режим разработчика в Discord",
                copy_user_id: "Скопируйте ваш Discord User ID",
                troubleshooting: "Диагностика",
                troubleshoot_intro: "Если что-то не работает, попробуйте:",
                troubleshoot_bot_perms: "Убедитесь, что бот онлайн и у него есть права",
                troubleshoot_id_correct: "Проверьте, что Discord ID верный (только цифры)",
                troubleshoot_waiting_room: "Убедитесь, что вы находитесь в голосовом канале Waiting Room",

                keep_open_note: "Держите эту страницу открытой во время игры. Приложение автоматически обновит статус, когда матч начнётся.",

                // Dynamic UI messages
                msg_copied: "Ссылка-приглашение скопирована в буфер обмена!",
                msg_copy_failed: "Не удалось скопировать ссылку. Скопируйте её вручную.",
                msg_opening_discord: "Открываю приглашение Discord...",
                msg_oauth_open: "Открываю авторизацию Discord...",
                msg_invalid_id: "Введите корректный Discord User ID (только цифры).",
                msg_saved: "Discord ID успешно сохранён.",
                                msg_save_failed: "Не удалось сохранить Discord ID. Попробуйте ещё раз.",

                // Дополнительные строки интерфейса для этой страницы
                doc_title: "Привязка Discord — LoL Voice Chat",
                card_discord_linking: "Привязка Discord",
                btn_change_discord_id: "Изменить Discord ID",
                loading_linking: "Привязываю аккаунт...",
                btn_link_manual: "Привязать Discord (вручную)",
                btn_refresh_status: "Обновить статус",
                voice_channel_prompt: "Матч начался! Подключайтесь к голосовому каналу вашей команды:",
                help_instructions: "Помощь и инструкции",
                how_to_find_discord_id: "Как найти Discord ID?",
                find_discord_id_steps: "Откройте Discord → Настройки → Расширенные → включите «Режим разработчика» → ПКМ по аватару → «Скопировать ID пользователя»",
                join_our_server: "Присоединяйтесь к серверу",
                make_sure_in_server: "Убедитесь, что вы на",
                our_discord_server: "нашем Discord-сервере",
                important_to_know: "Важно знать:",
                note_change_id: "Если нужно изменить Discord ID — нажмите кнопку «Изменить»",
                note_channels_created: "Голосовые каналы создаются автоматически после старта матча",
                note_auto_connected: "Вы будете автоматически подключены к каналу вашей команды",
                step_1: "Привяжите аккаунт",
                step_2: "Запустите League of Legends и начните матч",
                step_3: "После старта матча обновите статус",
                step_4: "Зайдите в голосовой канал команды!",
                lbl_channel: "Канал:",
                lbl_team_label: "Команда:",
                lbl_match: "Матч:",
                lbl_player: "Игрок",
                lbl_id: "ID",
                lbl_saved: "Сохранено",
                btn_account_linked: "Аккаунт привязан",
                msg_enter_new_id: "Введите новый Discord ID",
                msg_match_status_error: "Не удалось проверить статус матча. Убедитесь, что League of Legends запущена.",
                msg_match_started_ready: "✅ Матч начался! Голосовой канал готов.",
                msg_match_loading: "🔄 Идёт загрузка... Голосовой канал появится после старта матча.",
                msg_champ_select: "🎯 Выбор чемпионов... Голосовой канал будет создан после старта матча.",
                msg_match_found_not_started: "⏳ Матч найден, но ещё не начался. Голосовой канал появится после старта матча.",
                msg_no_active_match: "❌ Активный матч не найден. Запустите League of Legends и начните игру.",
                msg_voice_ready: "🎉 Матч начался! Голосовой канал вашей команды готов. Подключайтесь!",
                msg_already_linked: "✅ Discord уже привязан: {id}",
                msg_oauth_linked: "✅ Discord привязан через OAuth: {id}",
                server_user_found: "✅ Пользователь найден на сервере",
                server_user_not_found: "❌ Пользователь не найден на сервере",
                server_join_server: "Вступить на сервер",
                server_join_bot_server: "Пожалуйста, вступите на Discord-сервер бота.",
                server_status_unknown: "⚠️ Не удалось проверить статус",
                msg_auth_failed: "Не удалось авторизоваться. Запустите League of Legends и попробуйте ещё раз.",
                msg_oauth_timeout: "⏳ Окно авторизации открыто, но привязка ещё не обнаружена. Если вы завершили авторизацию, нажмите «Обновить статус».",
                msg_oauth_start_failed: "Не удалось запустить OAuth Discord.",
                msg_oauth_no_url: "Сервер не вернул ссылку на авторизацию.",
                msg_match_status_updated: "🔄 Статус матча обновлён",
                msg_copied_short: "Скопировано!"
            }
        };


        let currentLang = "en";

        function t(key) {
            const pack = I18N[currentLang] || I18N.en;
            return (pack && pack[key]) || I18N.en[key] || key;
        }

        function tFmt(key, vars) {
            let s = t(key);
            if (!vars) return s;
            for (const k in vars) {
                if (Object.prototype.hasOwnProperty.call(vars, k)) {
                    s = s.split(`{${k}}`).join(String(vars[k]));
                }
            }
            return s;
        }

        function applyTranslations() {
            document.querySelectorAll("[data-i18n]").forEach(el => {
                const key = el.getAttribute("data-i18n");
                el.textContent = t(key);
            });
            document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
                const key = el.getAttribute("data-i18n-placeholder");
                el.setAttribute("placeholder", t(key));
            });
        }

        function getInitialLang() {
            const saved = localStorage.getItem("lang");
            if (saved && (saved === "ru" || saved === "en")) return saved;
            const n = (navigator.language || "").toLowerCase();
            return n.startsWith("ru") ? "ru" : "en";
        }

        function setLang(lang) {
            currentLang = (lang === "ru" ? "ru" : "en");
            localStorage.setItem("lang", currentLang);
            document.documentElement.setAttribute("lang", currentLang);
            applyTranslations();
            // Update the browser/window title
            document.title = t('doc_title');
        }

        function getInitialTheme() {
            const saved = localStorage.getItem("theme");
            if (saved === "dark" || saved === "light") return saved;
            return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
        }

        function setTheme(theme) {
            const th = (theme === "dark") ? "dark" : "light";
            document.documentElement.dataset.theme = th;
            localStorage.setItem("theme", th);

            const icon = document.getElementById("themeIcon");
            if (icon) icon.textContent = (th === "dark") ? "☀️" : "🌙";
        }

        function toggleTheme() {
            const now = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
            setTheme(now);
        }

        function initPreferencesUI() {
            // Theme
            setTheme(getInitialTheme());
            const themeBtn = document.getElementById("themeToggle");
            if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

            // Language
            setLang(getInitialLang());
            const sel = document.getElementById("langSelect");
            if (sel) {
                sel.value = currentLang;
                sel.addEventListener("change", () => setLang(sel.value));
            }
        }

// DOM elements
        const form = document.getElementById('discordLinkForm');
        const discordIdInput = document.getElementById('discordId');
        const submitBtn = document.getElementById('submitBtn');
        const messageDiv = document.getElementById('message');
        const loadingDiv = document.getElementById('loading');
        const currentUserInfo = document.getElementById('currentUserInfo');
        const userDetails = document.getElementById('userDetails');
        const changeDiscordContainer = document.getElementById('changeDiscordContainer');
        const changeDiscordBtn = document.getElementById('changeDiscordBtn');
        const oauthLinkBtn = document.getElementById('oauthLinkBtn');
        const serverStatus = document.getElementById('serverStatus');
        const voiceChannelInfo = document.getElementById('voiceChannelInfo');
        const voiceInviteLink = document.getElementById('voiceInviteLink');
        const copyInviteBtn = document.getElementById('copyInviteBtn');
        const channelName = document.getElementById('channelName');
        const teamName = document.getElementById('teamName');
        const matchIdElement = document.getElementById('matchId');
        const matchStatus = document.getElementById('matchStatus');
        const matchStatusText = document.getElementById('matchStatusText');
        const refreshMatchBtn = document.getElementById('refreshMatchBtn');

        // Try to get current user information (via local LCU)
        async function loadCurrentUser() {
            try {
                const response = await fetch('/api/auth/auto-auth');
                if (!response.ok) {
                    let detail = '';
                    try {
                        const err = await response.json();
                        detail = err.detail || '';
                    } catch (_) {
                        // ignore
                    }

                    // Show a clear, actionable message when LoL is not running
                    matchStatus.style.display = 'block';
                    if (response.status === 503) {
                        matchStatusText.textContent = detail || t('msg_lol_not_running');
                    } else {
                        matchStatusText.textContent = detail || t('msg_auth_failed');
                    }
                    return;
                }

                const data = await response.json();
                if (!data || !data.summoner_name) return;

                userDetails.textContent = `${t('lbl_player')}: ${data.summoner_name} (${t('lbl_id')}: ${data.summoner_id})`;
                currentUserInfo.style.display = 'block';

                // Save token for subsequent requests
                localStorage.setItem('authToken', data.access_token);

                // Initial check and then real-time polling
                checkMatchStatus(data.summoner_id);
                if (!window._matchStatusPoller) {
                    window._matchStatusPoller = setInterval(() => {
                        checkMatchStatus(data.summoner_id);
                    }, 2000);
                }
            } catch (error) {
                matchStatus.style.display = 'block';
                matchStatusText.textContent = t('msg_lol_not_running');
            }
        }

        // Check match status and voice channels
        async function checkMatchStatus(summonerId) {
            try {
                const token = localStorage.getItem('authToken');
                if (!token) return;
                
                // Try new endpoint
                const matchInfoResponse = await fetch(`/api/discord/match-status/${summonerId}`, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (matchInfoResponse.ok) {
                    const matchInfo = await matchInfoResponse.json();
                    updateMatchStatusUI(matchInfo);
                } else if (matchInfoResponse.status === 404) {
                    // If endpoint not found, try old endpoint
                    console.log('match-status endpoint not found, trying user-match-info...');
                    const fallbackResponse = await fetch(`/api/discord/user-match-info/${summonerId}`, {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    
                    if (fallbackResponse.ok) {
                        const matchInfo = await fallbackResponse.json();
                        updateMatchStatusUI(matchInfo);
                    } else {
                        let detail = null;
                        try { detail = (await fallbackResponse.json()).detail; } catch (e) {}
                        showMatchStatusError(detail || t('msg_match_status_error'));
                    }
                } else {
                    let detail = null;
                    try { detail = (await matchInfoResponse.json()).detail; } catch (e) {}
                    showMatchStatusError(detail || t('msg_match_status_error'));
                }
            } catch (error) {
                console.log('Could not check match status:', error);
                showMatchStatusError();
            }
        }

        function showMatchStatusError(customMsg) {
            matchStatus.style.display = 'block';
            matchStatusText.textContent = customMsg || t('msg_match_status_error');
        }

        // Update UI based on match status
        function updateMatchStatusUI(matchInfo) {
            matchStatus.style.display = 'block';
            
            if (matchInfo.in_progress && matchInfo.voice_channel) {
                // Match STARTED (InProgress) and voice channel is available
                matchStatusText.textContent = t('msg_match_started_ready');
                displayVoiceChannelInfo(matchInfo);
            } else if (matchInfo.in_loading_screen) {
                // Loading screen - don't show link
                matchStatusText.textContent = t('msg_match_loading');
                voiceChannelInfo.style.display = 'none';
            } else if (matchInfo.in_champ_select) {
                // Champion selection in progress
                matchStatusText.textContent = t('msg_champ_select');
                voiceChannelInfo.style.display = 'none';
            } else if (matchInfo.match_id && !matchInfo.in_progress) {
                // Match found but not started yet
                matchStatusText.textContent = t('msg_match_found_not_started');
                voiceChannelInfo.style.display = 'none';
            } else {
                // No active match
                matchStatusText.textContent = t('msg_no_active_match');
                voiceChannelInfo.style.display = 'none';
            }
        }

        // Display voice channel information (only after match starts)
        function displayVoiceChannelInfo(matchInfo) {
            if (matchInfo.voice_channel && matchInfo.voice_channel.invite_url) {
                voiceInviteLink.href = matchInfo.voice_channel.invite_url;
                channelName.textContent = matchInfo.voice_channel.channel_name;
                teamName.textContent = matchInfo.team_name;
                matchIdElement.textContent = matchInfo.match_id;
                voiceChannelInfo.style.display = 'block';
                
                // Show notification about successful channel creation
                showMessage(t('msg_voice_ready'), 'success');
            }
        }

        // Check if Discord is already linked
        async function checkExistingLink() {
            try {
                const token = localStorage.getItem('authToken');
                if (!token) return;
                
                const response = await fetch('/api/discord/linked-account', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.discord_user_id) {
                        showMessage(tFmt('msg_already_linked', { id: data.discord_user_id }), 'success');
                        lockForm(data.discord_user_id);
                        // Check server status
                        checkServerStatus(data.discord_user_id);
                    }
                }
            } catch (error) {
                console.log('Could not check linked account');
            }
        }

        // Function to lock UI when account is linked
        function lockForm(discordId) {
            // We keep a hidden field only for internal state; users do not enter IDs manually.
            if (discordIdInput) {
                discordIdInput.value = discordId;
                discordIdInput.disabled = true;
            }
            if (oauthLinkBtn) { oauthLinkBtn.disabled = true; }
            if (changeDiscordContainer) { changeDiscordContainer.style.display = 'block'; }
        }

        // Function to unlock UI (used when unlinking)
        function unlockForm() {
            if (discordIdInput) {
                discordIdInput.value = '';
                discordIdInput.disabled = true;
            }
            if (oauthLinkBtn) { oauthLinkBtn.disabled = false; }
            if (changeDiscordContainer) { changeDiscordContainer.style.display = 'none'; }
            if (messageDiv) { messageDiv.style.display = 'none'; }
            if (serverStatus) { serverStatus.style.display = 'none'; }
            if (voiceChannelInfo) { voiceChannelInfo.style.display = 'none'; }
        }

        // Show messages // Show messages
        function showMessage(text, type) {
            messageDiv.textContent = text;
            messageDiv.className = `message ${type}`;
            messageDiv.style.display = 'block';
            
            // Auto-hide success messages
            if (type === 'success') {
                setTimeout(() => {
                    messageDiv.style.display = 'none';
                }, 5000);
            }
        }

        // Discord ID validation
        function isValidDiscordId(id) {
            return /^\d+$/.test(id) && id.length >= 17 && id.length <= 20;
        }

        // Check user status on server
        async function checkServerStatus(discordId) {
            if (!discordId || !isValidDiscordId(discordId)) return;
            
            try {
                const token = localStorage.getItem('authToken');
                if (!token) return;
                
                const response = await fetch(`/api/discord/user-server-status/${discordId}`, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const status = await response.json();
                    updateServerStatusUI(status);
                }
            } catch (error) {
                console.log('Could not check server status');
            }
        }

        // Update UI with status
        function updateServerStatusUI(status) {
            if (!status) return;
            
            serverStatus.style.display = 'block';
            
            if (status.on_server === true) {
                serverStatus.innerHTML = t('server_user_found');
                serverStatus.className = 'server-status success';
            } else if (status.on_server === false) {
                let message = t('server_user_not_found');
                if (status.server_invite_available) {
                    message += `<br><a href="${status.server_invite}" target="_blank" style="color: var(--primary); text-decoration: underline;">${t("server_join_server")}</a>`;
                } else {
                    message += '<br>' + t('server_join_bot_server');
                }
                serverStatus.innerHTML = message;
                serverStatus.className = 'server-status error';
            } else {
                serverStatus.innerHTML = t('server_status_unknown');
                serverStatus.className = 'server-status warning';
            }
        }


async function ensureAuthToken() {
    let token = localStorage.getItem('authToken');
    if (token) return token;
    const authResponse = await fetch('/api/auth/auto-auth');
    if (authResponse.ok) {
        const authData = await authResponse.json();
        token = authData.access_token;
        if (token) localStorage.setItem('authToken', token);
    }
    return token;
}

async function startDiscordOAuthLink() {
    try {
        const token = await ensureAuthToken();
        if (!token) {
            showMessage('❌ ' + t('msg_auth_failed'), 'error');
            return;
        }

        if (oauthLinkBtn) oauthLinkBtn.disabled = true;
        showMessage('🔐 ' + t('msg_oauth_open'), 'success');

        const resp = await fetch('/api/auth/discord/login-url', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            const msg = (data && (data.detail || data.message)) ? (data.detail || data.message) : t('msg_oauth_start_failed');
            throw new Error(msg);
        }

        const url = data.url;
        if (!url) throw new Error(t('msg_oauth_no_url'));

        // Open externally (best UX). Falls back to window.open.
        try {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.open_browser) {
                await window.pywebview.api.open_browser(url);
            } else {
                window.open(url, '_blank');
            }
        } catch (e) {
            window.open(url, '_blank');
        }

        // Poll linked-account to detect completion
        const startedAt = Date.now();
        const timeoutMs = 120000; // 2 minutes
        const interval = setInterval(async () => {
            try {
                const token2 = localStorage.getItem('authToken');
                if (!token2) return;

                const check = await fetch('/api/discord/linked-account', {
                    headers: { 'Authorization': `Bearer ${token2}` }
                });

                if (check.ok) {
                    const info = await check.json();
                    if (info.discord_user_id) {
                        clearInterval(interval);
                        showMessage(tFmt('msg_oauth_linked', { id: info.discord_user_id }), 'success');
                        lockForm(info.discord_user_id);
                        checkServerStatus(info.discord_user_id);
                    }
                }

                if (Date.now() - startedAt > timeoutMs) {
                    clearInterval(interval);
                    if (oauthLinkBtn) oauthLinkBtn.disabled = false;
                    showMessage(t('msg_oauth_timeout'), 'warning');
                }
            } catch (e) {
                // ignore
            }
        }, 2000);
    } catch (error) {
        console.error('OAuth link error:', error);
        showMessage(`❌ ${error.message}`, 'error');
        if (oauthLinkBtn) oauthLinkBtn.disabled = false;
    }
}

        // Manual Discord ID linking has been removed.
        // Prevent form submit (Enter key) and redirect users to OAuth...


// Handler for OAuth linking button
if (oauthLinkBtn) {
    oauthLinkBtn.addEventListener('click', function() {
        startDiscordOAuthLink();
    });
}

        // Handler for change Discord button (re-link via OAuth)
        if (changeDiscordBtn) {
            changeDiscordBtn.addEventListener('click', function() {
                startDiscordOAuthLink();
            });
        }

        // Handler for refresh match status button
        refreshMatchBtn.addEventListener('click', function() {
            const token = localStorage.getItem('authToken');
            if (!token) return;
            
            fetch('/api/auth/auto-auth')
                .then(response => response.json())
                .then(data => {
                    if (data.summoner_id) {
                        checkMatchStatus(data.summoner_id);
                        showMessage(t('msg_match_status_updated'), 'success');
                    }
                })
                .catch(error => {
                    console.log('Error updating match status');
                });
        });

        // Handler for copy link button
        copyInviteBtn.addEventListener('click', function() {
            const inviteUrl = voiceInviteLink.href;
            navigator.clipboard.writeText(inviteUrl).then(() => {
                const originalText = copyInviteBtn.textContent;
                copyInviteBtn.innerHTML = '<i class="fas fa-check"></i> ' + t('msg_copied_short');
                setTimeout(() => {
                    copyInviteBtn.innerHTML = '<i class="far fa-copy"></i> ' + t('btn_copy_link');
                }, 2000);
            }).catch(err => {
                console.error('Copy error: ', err);
                showMessage('❌ ' + t('msg_copy_failed'), 'error');
            });
        });

        // Real-time validation
        discordIdInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (value && !isValidDiscordId(value)) {
                this.style.borderColor = 'var(--danger)';
            } else {
                this.style.borderColor = '#e1e5e9';
                // Check status when ID is valid
                if (isValidDiscordId(value) && !this.disabled) {
                    checkServerStatus(value);
                }
            }
        });
        // Show the "manual link" button only when the advanced Discord ID section is opened
        function setupManualLinkVisibility() {
            const submitBtn = document.getElementById('submitBtn');
            const discordIdInput = document.getElementById('discordId');
            if (!submitBtn || !discordIdInput) return;

            const manualDetails = discordIdInput.closest('details');
            if (!manualDetails) return;

            const sync = () => {
                const shouldShow = !!manualDetails.open;
                submitBtn.style.display = shouldShow ? '' : 'none';
                submitBtn.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
            };

            manualDetails.addEventListener('toggle', sync);
            sync();
        }



        // Load information when page loads
        document.addEventListener('DOMContentLoaded', () => {
            
            
            setupManualLinkVisibility();
initPreferencesUI();
            loadCurrentUser();
            setTimeout(() => checkExistingLink(), 1000);
        });
