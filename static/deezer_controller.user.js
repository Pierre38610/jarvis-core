// ==UserScript==
// @name         Deezer Controller for J.A.R.V.I.S.
// @namespace    https://github.com/Pierre38610/jarvis-core
// @version      2.0.0
// @description  Contrôle total du Web Player Deezer en temps réel via WebSocket pour J.A.R.V.I.S.
// @author       Pierre / J.A.R.V.I.S.
// @match        https://www.deezer.com/*
// @icon         https://www.deezer.com/favicon.ico
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    console.log('[J.A.R.V.I.S. Deezer Controller] Initialisation du contrôleur Web Player...');

    const WS_URL = 'ws://localhost:8765';
    const RECONNECT_DELAY = 3000;
    let ws = null;
    let reconnectTimer = null;
    let isConnected = false;
    let lastSentStatusJson = '';
    let lastTimeupdateSent = 0;

    // ─── GESTION DU HUD VISUEL DISCRET ──────────────────────────────────────────

    function createHUD() {
        if (document.getElementById('jarvis-deezer-hud')) return;

        const hud = document.createElement('div');
        hud.id = 'jarvis-deezer-hud';
        hud.innerHTML = `
            <div id="jarvis-status-badge">
                <span id="jarvis-status-dot"></span>
                <span id="jarvis-status-text">J.A.R.V.I.S. Déconnecté</span>
            </div>
            <div id="jarvis-toast" style="display: none;"></div>
        `;

        const style = document.createElement('style');
        style.textContent = `
            #jarvis-deezer-hud {
                position: fixed;
                bottom: 84px;
                right: 20px;
                z-index: 999999;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                pointer-events: none;
                user-select: none;
            }
            #jarvis-status-badge {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 12px;
                background: rgba(15, 23, 42, 0.85);
                backdrop-filter: blur(8px);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 9999px;
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 600;
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
                transition: all 0.3s ease;
            }
            #jarvis-status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #ef4444;
                box-shadow: 0 0 8px #ef4444;
                transition: all 0.3s ease;
            }
            #jarvis-status-dot.connected {
                background: #10b981;
                box-shadow: 0 0 10px #10b981;
            }
            #jarvis-toast {
                margin-top: 6px;
                padding: 5px 10px;
                background: rgba(14, 165, 233, 0.9);
                border-radius: 6px;
                color: #ffffff;
                font-size: 10px;
                font-weight: 500;
                text-align: center;
                animation: jarvisFadeIn 0.2s ease;
            }
            @keyframes jarvisFadeIn {
                from { opacity: 0; transform: translateY(4px); }
                to { opacity: 1; transform: translateY(0); }
            }
        `;

        document.head.appendChild(style);
        document.body.appendChild(hud);
    }

    function updateHUD(connected, message = null) {
        const dot = document.getElementById('jarvis-status-dot');
        const text = document.getElementById('jarvis-status-text');
        if (dot && text) {
            if (connected) {
                dot.className = 'connected';
                text.textContent = 'J.A.R.V.I.S. Connecté';
            } else {
                dot.className = '';
                text.textContent = 'J.A.R.V.I.S. Déconnecté';
            }
        }
        if (message) {
            showToast(message);
        }
    }

    function showToast(msg) {
        const toast = document.getElementById('jarvis-toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.style.display = 'block';
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.style.display = 'none';
        }, 2500);
    }

    // ─── SÉLECTEURS ROBUSTES AVEC FALLBACKS ────────────────────────────────────

    const SELECTORS = {
        playPause: [
            'button[data-testid="play_button"]',
            'button[data-testid="play_button_play"]',
            'button[data-testid="play_button_pause"]',
            'button[data-testid="player-play"]',
            'button[data-testid="player-pause"]',
            'button[aria-label="Lecture"]',
            'button[aria-label="Pause"]',
            'button[aria-label="Play"]',
            'button[aria-label*="Lecture" i]',
            'button[aria-label*="Pause" i]',
            'button[aria-label*="Play" i]'
        ],
        next: [
            'button[data-testid="next_track_button"]',
            'button[data-testid="next_button"]',
            'button[data-testid="player-next"]',
            'button[aria-label="Piste suivante"]',
            'button[aria-label="Next track"]',
            'button[aria-label*="suivante" i]',
            'button[aria-label*="next" i]'
        ],
        previous: [
            'button[data-testid="previous_track_button"]',
            'button[data-testid="prev_button"]',
            'button[data-testid="player-previous"]',
            'button[aria-label="Piste précédente"]',
            'button[aria-label="Previous track"]',
            'button[aria-label*="précédente" i]',
            'button[aria-label*="previous" i]'
        ],
        shuffle: [
            'button[data-testid="shuffle_button"]',
            'button[data-testid="player-shuffle"]',
            'button[aria-label*="aléatoire" i]',
            'button[aria-label*="shuffle" i]'
        ],
        repeat: [
            'button[data-testid="repeat_button"]',
            'button[data-testid="player-repeat"]',
            'button[aria-label*="répéter" i]',
            'button[aria-label*="repeat" i]'
        ],
        volumeSlider: [
            'input[type="range"][data-testid="volume_slider"]',
            'input[type="range"][aria-label*="volume" i]',
            '.slider-volume input[type="range"]'
        ],
        title: [
            '[data-testid="item_title"] a',
            '[data-testid="item_title"]',
            '.track-title',
            '[data-testid="player-track-title"]',
            '.marquee-track-title'
        ],
        artist: [
            '[data-testid="item_subtitle"] a',
            '[data-testid="item_subtitle"]',
            '.track-artist',
            '[data-testid="player-track-artist"]',
            '.marquee-track-artist'
        ],
        cover: [
            '[data-testid="player-cover"] img',
            '.marquee-track-cover img',
            'img[data-testid="cover"]',
            '#page_player img'
        ],
        pagePlay: [
            'button[data-testid="item_play_button"]',
            'button[data-testid="item_top_banner_play_button"]',
            'button[data-testid="masthead-play-button"]',
            'button[aria-label="Écouter"]',
            'button[aria-label="Tout écouter"]',
            'button[aria-label="Play"]',
            'button[aria-label="Listen"]',
            'button[data-testid="track_play_button"]',
            'button[data-testid="play_button"]'
        ]
    };

    function findFirstElement(selectors) {
        for (const selector of selectors) {
            try {
                const el = document.querySelector(selector);
                if (el) return el;
            } catch (e) {}
        }
        return null;
    }

    function getAudioElement() {
        return document.querySelector('audio');
    }

    function isShuffleActive() {
        const btn = findFirstElement(SELECTORS.shuffle);
        if (!btn) return false;
        const ariaChecked = btn.getAttribute('aria-checked');
        if (ariaChecked !== null) return ariaChecked === 'true';
        const ariaPressed = btn.getAttribute('aria-pressed');
        if (ariaPressed !== null) return ariaPressed === 'true';
        return btn.classList.contains('is-active') || btn.classList.contains('active');
    }

    function getRepeatMode() {
        const btn = findFirstElement(SELECTORS.repeat);
        if (!btn) return 'off';
        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (ariaLabel.includes('un seul') || ariaLabel.includes('one')) return 'one';
        if (ariaLabel.includes('désactivé') || ariaLabel.includes('off')) return 'off';
        if (btn.classList.contains('is-active') || btn.classList.contains('active')) return 'all';
        return 'off';
    }

    // ─── RÉCUPÉRATION DU STATUT COMPLET ───────────────────────────────────────

    function getStatus() {
        const audio = getAudioElement();
        const titleEl = findFirstElement(SELECTORS.title);
        const artistEl = findFirstElement(SELECTORS.artist);
        const coverEl = findFirstElement(SELECTORS.cover);

        let isPlaying = false;
        if (audio) {
            isPlaying = !audio.paused && !audio.ended && audio.currentTime > 0;
        } else {
            const pauseBtn = document.querySelector('button[data-testid="play_button_pause"], button[aria-label="Pause"], svg[data-testid="Pause"]');
            isPlaying = Boolean(pauseBtn);
        }

        let title = titleEl ? (titleEl.textContent || '').trim() : '';
        let artist = artistEl ? (artistEl.textContent || '').trim() : '';
        const cover = coverEl ? coverEl.src : '';

        if (!title && document.title && document.title.includes('·')) {
            const parts = document.title.split('·');
            title = parts[0].trim();
            if (parts.length > 1) artist = parts[1].replace('- Deezer', '').trim();
        }

        const currentTime = audio ? audio.currentTime : 0;
        const duration = audio ? audio.duration || 0 : 0;
        const volume = audio ? Math.round(audio.volume * 100) : 100;

        return {
            title: title || 'Inconnu',
            artist: artist || '',
            album: '',
            cover: cover || '',
            is_playing: isPlaying,
            shuffle: isShuffleActive(),
            repeat: getRepeatMode(),
            current_time: Math.round(currentTime * 10) / 10,
            duration: Math.round(duration * 10) / 10,
            volume: volume,
            url: window.location.href
        };
    }

    function sendStatusUpdate(force = false) {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const status = getStatus();
        const statusJson = JSON.stringify(status);

        if (force || statusJson !== lastSentStatusJson) {
            lastSentStatusJson = statusJson;
            try {
                ws.send(JSON.stringify({
                    type: 'status',
                    data: status
                }));
            } catch (e) {
                console.error('[J.A.R.V.I.S. Deezer] Erreur envoi statut :', e);
            }
        }
    }

    // ─── ÉCOUTEURS D'ÉVÉNEMENTS AUDIO & DOM ────────────────────────────────────

    let currentAudioEl = null;

    function attachAudioListeners() {
        const audio = getAudioElement();
        if (audio && audio !== currentAudioEl) {
            currentAudioEl = audio;
            ['play', 'pause', 'ended', 'volumechange', 'loadedmetadata'].forEach(evt => {
                audio.addEventListener(evt, () => {
                    sendStatusUpdate(true);
                });
            });

            audio.addEventListener('timeupdate', () => {
                const now = Date.now();
                if (now - lastTimeupdateSent > 2000) {
                    lastTimeupdateSent = now;
                    sendStatusUpdate(false);
                }
            });
            console.log('[J.A.R.V.I.S. Deezer] Écouteurs audio HTML5 attachés avec succès.');
        }
    }

    const observer = new MutationObserver(() => {
        attachAudioListeners();
        checkPendingAutoplay();
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });

    // ─── AUTOPLAY INTELLIGENT APRÈS NAVIGATION ────────────────────────────────

    function checkPendingAutoplay() {
        const pendingJson = sessionStorage.getItem('jarvis_deezer_autoplay');
        if (!pendingJson) return;

        try {
            const pending = JSON.parse(pendingJson);
            const now = Date.now();
            if (now - pending.time > 30000) {
                sessionStorage.removeItem('jarvis_deezer_autoplay');
                return;
            }

            const playBtn = findFirstElement(SELECTORS.pagePlay);
            if (playBtn) {
                console.log('[J.A.R.V.I.S. Deezer] Bouton Play détecté sur la page, déclenchement...');
                playBtn.click();
                showToast('Lecture auto J.A.R.V.I.S.');
                sessionStorage.removeItem('jarvis_deezer_autoplay');
                setTimeout(() => sendStatusUpdate(true), 500);
            }
        } catch (e) {
            sessionStorage.removeItem('jarvis_deezer_autoplay');
        }
    }

    // ─── GESTION DES COMMANDES REÇUES ─────────────────────────────────────────

    async function handleCommand(msg) {
        const action = msg.action;
        const params = msg.params || {};
        const cmdId = msg.command_id;

        console.log(`[J.A.R.V.I.S. Deezer] Commande reçue : ${action}`, params);
        let success = true;
        let responseMessage = 'Action exécutée avec succès.';

        try {
            switch (action) {
                case 'play': {
                    const audio = getAudioElement();
                    if (audio && audio.paused) {
                        try { await audio.play(); } catch (e) {}
                    }
                    const playBtn = findFirstElement(SELECTORS.playPause);
                    if (playBtn) playBtn.click();
                    showToast('▶ Lecture');
                    break;
                }

                case 'pause': {
                    const audio = getAudioElement();
                    if (audio && !audio.paused) {
                        try { audio.pause(); } catch (e) {}
                    }
                    const pauseBtn = document.querySelector('button[data-testid="play_button_pause"], button[aria-label="Pause"]') || findFirstElement(SELECTORS.playPause);
                    if (pauseBtn) pauseBtn.click();
                    showToast('⏸ Pause');
                    break;
                }

                case 'toggle_play': {
                    const playBtn = findFirstElement(SELECTORS.playPause);
                    if (playBtn) {
                        playBtn.click();
                    } else {
                        const audio = getAudioElement();
                        if (audio) {
                            if (audio.paused) await audio.play();
                            else audio.pause();
                        }
                    }
                    showToast('⏯ Play / Pause');
                    break;
                }

                case 'next': {
                    const nextBtn = findFirstElement(SELECTORS.next);
                    if (nextBtn) {
                        nextBtn.click();
                        showToast('⏭ Piste suivante');
                    } else {
                        success = false;
                        responseMessage = 'Bouton suivant introuvable.';
                    }
                    break;
                }

                case 'previous': {
                    const prevBtn = findFirstElement(SELECTORS.previous);
                    if (prevBtn) {
                        prevBtn.click();
                        showToast('⏮ Piste précédente');
                    } else {
                        success = false;
                        responseMessage = 'Bouton précédent introuvable.';
                    }
                    break;
                }

                case 'set_shuffle': {
                    const shuffleBtn = findFirstElement(SELECTORS.shuffle);
                    if (shuffleBtn) {
                        const current = isShuffleActive();
                        const target = params.enable !== undefined ? Boolean(params.enable) : !current;
                        if (current !== target) {
                            shuffleBtn.click();
                        }
                        showToast(target ? '🔀 Aléatoire : Activé' : '➡️ Aléatoire : Désactivé');
                    } else {
                        success = false;
                        responseMessage = 'Bouton shuffle introuvable.';
                    }
                    break;
                }

                case 'set_repeat': {
                    const repeatBtn = findFirstElement(SELECTORS.repeat);
                    if (repeatBtn) {
                        repeatBtn.click();
                        showToast('🔁 Répétition basculée');
                    } else {
                        success = false;
                        responseMessage = 'Bouton repeat introuvable.';
                    }
                    break;
                }

                case 'set_volume': {
                    const vol = Math.max(0, Math.min(100, parseInt(params.volume ?? 100)));
                    const audio = getAudioElement();
                    if (audio) {
                        audio.volume = vol / 100;
                    }
                    const slider = findFirstElement(SELECTORS.volumeSlider);
                    if (slider) {
                        slider.value = vol;
                        slider.dispatchEvent(new Event('input', { bubbles: true }));
                        slider.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    showToast(`🔊 Volume : ${vol}%`);
                    break;
                }

                case 'seek': {
                    const audio = getAudioElement();
                    let pos = parseFloat(params.position ?? 0);
                    if (params.offset !== undefined && audio) {
                        pos = audio.currentTime + parseFloat(params.offset);
                    }
                    if (audio) {
                        audio.currentTime = Math.max(0, Math.min(audio.duration || 9999, pos));
                        showToast(`⏱ ${Math.round(pos)}s`);
                    } else {
                        success = false;
                        responseMessage = 'Élément audio introuvable pour seek.';
                    }
                    break;
                }

                case 'play_url': {
                    const url = params.url;
                    if (!url) {
                        success = false;
                        responseMessage = 'URL manquante.';
                        break;
                    }

                    sessionStorage.setItem('jarvis_deezer_autoplay', JSON.stringify({
                        url: url,
                        time: Date.now()
                    }));

                    const currentClean = window.location.href.split('?')[0].replace(/\/$/, '');
                    const targetClean = url.split('?')[0].replace(/\/$/, '');

                    if (currentClean === targetClean) {
                        checkPendingAutoplay();
                    } else {
                        showToast('Chargement musique...');
                        window.location.href = url;
                    }
                    break;
                }

                case 'get_status': {
                    break;
                }

                default:
                    success = false;
                    responseMessage = `Action inconnue : ${action}`;
            }
        } catch (err) {
            success = false;
            responseMessage = `Erreur : ${err.message}`;
            console.error('[J.A.R.V.I.S. Deezer] Erreur action :', err);
        }

        await new Promise(r => setTimeout(r, 200));

        const updatedStatus = getStatus();

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'response',
                command_id: cmdId,
                status: success ? 'success' : 'error',
                action: action,
                message: responseMessage,
                data: updatedStatus
            }));
        }
    }

    // ─── GESTIONNAIRE DE CONNEXION WEBSOCKET ──────────────────────────────────

    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        try {
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                isConnected = true;
                console.log('✅ [J.A.R.V.I.S. Deezer] Connecté au serveur Python local (ws://localhost:8765)');
                updateHUD(true, 'Connecté à J.A.R.V.I.S.');
                clearTimeout(reconnectTimer);
                attachAudioListeners();
                sendStatusUpdate(true);
                checkPendingAutoplay();
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'command') {
                        handleCommand(msg);
                    }
                } catch (e) {
                    console.error('[J.A.R.V.I.S. Deezer] Message non JSON reçu :', event.data);
                }
            };

            ws.onerror = () => {};

            ws.onclose = () => {
                isConnected = false;
                updateHUD(false);
                scheduleReconnect();
            };

        } catch (e) {
            isConnected = false;
            updateHUD(false);
            scheduleReconnect();
        }
    }

    function scheduleReconnect() {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY);
    }

    // Initialisation
    window.addEventListener('load', () => {
        createHUD();
        connectWebSocket();
        attachAudioListeners();
        checkPendingAutoplay();
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        createHUD();
        connectWebSocket();
        attachAudioListeners();
        checkPendingAutoplay();
    }

})();
