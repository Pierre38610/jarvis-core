// ==UserScript==
// @name         Deezer Controller for J.A.R.V.I.S.
// @namespace    https://github.com/Pierre38610/jarvis-core
// @version      2.1.0
// @description  Contrôle total du Web Player Deezer en temps réel via WebSocket pour J.A.R.V.I.S.
// @author       Pierre / J.A.R.V.I.S.
// @match        https://www.deezer.com/*
// @icon         https://www.deezer.com/favicon.ico
// @grant        unsafeWindow
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    console.log('[J.A.R.V.I.S. Deezer Controller v2.1.0] Démarrage du contrôleur Web Player...');

    const win = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
    const WS_URL = 'ws://localhost:8765';
    const RECONNECT_DELAY = 3000;
    let ws = null;
    let reconnectTimer = null;
    let isConnected = false;
    let lastSentStatusJson = '';
    let lastTimeupdateSent = 0;
    let autoplayPollTimer = null;

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
                padding: 6px 14px;
                background: rgba(15, 23, 42, 0.90);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 9999px;
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 600;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
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
                padding: 6px 12px;
                background: rgba(14, 165, 233, 0.95);
                border-radius: 8px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                text-align: center;
                box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
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
        }, 3000);
    }

    // ─── CLIC ROBUSTE POUR REACT / SYNTHETIC EVENTS ─────────────────────────────

    function robustClick(el) {
        if (!el) return false;
        try {
            el.focus();
            el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        } catch (e) {}

        const eventInit = {
            bubbles: true,
            cancelable: true,
            view: window,
            composed: true,
            buttons: 1
        };

        try { el.dispatchEvent(new PointerEvent('pointerdown', eventInit)); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('mousedown', eventInit)); } catch (e) {}
        try { el.dispatchEvent(new PointerEvent('pointerup', eventInit)); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('mouseup', eventInit)); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('click', eventInit)); } catch (e) {}
        try { el.click(); } catch (e) {}
        return true;
    }

    function triggerKey(code, key, shift = false) {
        const keyCodeMap = { 'Space': 32, 'ArrowRight': 39, 'ArrowLeft': 37, 'KeyK': 75, 'KeyS': 83 };
        const kCode = keyCodeMap[code] || 0;
        const opts = {
            key: key,
            code: code,
            keyCode: kCode,
            which: kCode,
            shiftKey: shift,
            bubbles: true,
            cancelable: true,
            composed: true
        };
        try {
            window.dispatchEvent(new KeyboardEvent('keydown', opts));
            document.dispatchEvent(new KeyboardEvent('keydown', opts));
            window.dispatchEvent(new KeyboardEvent('keyup', opts));
            document.dispatchEvent(new KeyboardEvent('keyup', opts));
        } catch (e) {}
    }

    function dismissCookieBanner() {
        const cookieSelectors = [
            '#didomi-notice-agree-button',
            'button#didomi-notice-agree-button',
            '#onetrust-accept-btn-handler',
            'button[data-testid="cookie-banner-accept"]',
            'button[aria-label*="accepter" i]',
            'button[aria-label*="agree" i]'
        ];
        for (const s of cookieSelectors) {
            const btn = document.querySelector(s);
            if (btn) {
                try {
                    btn.click();
                    console.log('[J.A.R.V.I.S. Deezer] Bannière cookies acceptée automatiquement.');
                } catch (e) {}
                break;
            }
        }
    }

    function getAudioElement() {
        return document.querySelector('audio');
    }

    function getBottomPlayer() {
        return document.querySelector('#page_player, [data-testid="player-bottom"], [data-testid="player"], footer');
    }

    function isShuffleActive() {
        const bottom = getBottomPlayer() || document;
        const btn = bottom.querySelector('button[data-testid="shuffle_button"], button[data-testid="player-shuffle"], button[aria-label*="aléatoire" i], button[aria-label*="shuffle" i]');
        if (!btn) return false;
        const ariaChecked = btn.getAttribute('aria-checked');
        if (ariaChecked !== null) return ariaChecked === 'true';
        const ariaPressed = btn.getAttribute('aria-pressed');
        if (ariaPressed !== null) return ariaPressed === 'true';
        return btn.classList.contains('is-active') || btn.classList.contains('active');
    }

    function getRepeatMode() {
        const bottom = getBottomPlayer() || document;
        const btn = bottom.querySelector('button[data-testid="repeat_button"], button[data-testid="player-repeat"], button[aria-label*="répéter" i], button[aria-label*="repeat" i]');
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
        const bottom = getBottomPlayer();

        let isPlaying = false;
        if (audio) {
            isPlaying = !audio.paused && !audio.ended && audio.currentTime > 0;
        } else {
            const pauseBtn = document.querySelector('button[data-testid="play_button_pause"], button[aria-label="Pause"], svg[data-testid="Pause"]');
            isPlaying = Boolean(pauseBtn);
        }

        let titleEl = bottom ? bottom.querySelector('[data-testid="item_title"] a, [data-testid="item_title"], .track-title, [data-testid="player-track-title"], .marquee-track-title') : null;
        if (!titleEl) {
            titleEl = document.querySelector('[data-testid="player-track-title"], .track-title');
        }

        let artistEl = bottom ? bottom.querySelector('[data-testid="item_subtitle"] a, [data-testid="item_subtitle"], .track-artist, [data-testid="player-track-artist"], .marquee-track-artist') : null;
        if (!artistEl) {
            artistEl = document.querySelector('[data-testid="player-track-artist"], .track-artist');
        }

        let coverEl = bottom ? bottom.querySelector('[data-testid="player-cover"] img, .marquee-track-cover img, img[data-testid="cover"]') : null;
        if (!coverEl) {
            coverEl = document.querySelector('[data-testid="player-cover"] img, #page_player img');
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

    // ─── ÉCOUTEURS D'ÉVÉNEMENTS AUDIO & OBSERVATEUR DOM ───────────────────────

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
            console.log('[J.A.R.V.I.S. Deezer] Écouteurs audio HTML5 attachés.');
        }
    }

    const observer = new MutationObserver(() => {
        attachAudioListeners();
        dismissCookieBanner();
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });

    // ─── AUTOPLAY INTELLIGENT ET ROBUSTE ──────────────────────────────────────

    function startAutoplayPolling(expectedType = null, expectedId = null) {
        if (autoplayPollTimer) {
            clearInterval(autoplayPollTimer);
            autoplayPollTimer = null;
        }

        console.log(`[J.A.R.V.I.S. Deezer] Démarrage polling autoplay (type: ${expectedType}, id: ${expectedId})...`);
        const startTime = Date.now();
        let clickAttempts = 0;

        autoplayPollTimer = setInterval(() => {
            const elapsed = Date.now() - startTime;
            if (elapsed > 15000) {
                console.log('[J.A.R.V.I.S. Deezer] Timeout polling autoplay (15s).');
                clearInterval(autoplayPollTimer);
                autoplayPollTimer = null;
                sessionStorage.removeItem('jarvis_dz_pending');
                return;
            }

            dismissCookieBanner();

            // 1. Si audio déjà en lecture, mission accomplie !
            const audio = getAudioElement();
            if (audio && !audio.paused && audio.currentTime > 0) {
                console.log('✅ [J.A.R.V.I.S. Deezer] Lecture active détectée ! Autoplay réussi.');
                clearInterval(autoplayPollTimer);
                autoplayPollTimer = null;
                sessionStorage.removeItem('jarvis_dz_pending');
                showToast('▶ Lecture en cours');
                setTimeout(() => sendStatusUpdate(true), 300);
                return;
            }

            // 2. Si intention Flow
            if (expectedType === 'flow' || window.location.href.includes('/channels/flow')) {
                const flowBtn = document.querySelector('button[data-testid="flow-button"], [data-testid="flow"] button, button[aria-label*="Flow" i]');
                if (flowBtn) {
                    console.log('[J.A.R.V.I.S. Deezer] Bouton Flow trouvé, clic...');
                    robustClick(flowBtn);
                    clickAttempts++;
                    return;
                }
            }

            // 3. Bouton Play principal de la page (UNIQUEMENT dans le contenu principal, JAMAIS dans la barre inférieure)
            const mainContent = document.querySelector('main, #page_naboo_item, #page_content, .page-content, [data-testid="item-header"]') || document.body;
            
            const heroPlaySelectors = [
                'main button[data-testid="item_play_button"]',
                'main button[data-testid="item_top_banner_play_button"]',
                'main button[data-testid="masthead-play-button"]',
                'main button[data-testid="action-play"]',
                'main [data-testid="item-header"] button',
                'main button[aria-label*="Tout écouter" i]',
                'main button[aria-label*="Écouter la playlist" i]',
                'main button[aria-label*="Écouter l\'album" i]',
                'main button[aria-label*="Écouter" i]',
                'main button[aria-label*="Play" i]',
                // Piste 1 de la tracklist
                'main [data-testid="tracklist-row"]:first-child button',
                'main [data-testid="datagrid-row"]:first-child button',
                'main [role="row"]:nth-of-type(2) button',
                'main table tbody tr:first-child button',
                'main [data-testid="tracklist-row"]:first-child',
                'main [role="row"]:nth-of-type(2)'
            ];

            for (const sel of heroPlaySelectors) {
                const el = document.querySelector(sel);
                if (el) {
                    console.log(`[J.A.R.V.I.S. Deezer] Bouton Play hero détecté (${sel}), clic...`);
                    robustClick(el);
                    clickAttempts++;
                    if (clickAttempts >= 3) {
                        try { el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); } catch (e) {}
                    }
                    break;
                }
            }
        }, 250);
    }

    function checkPendingAutoplay() {
        const pendingJson = sessionStorage.getItem('jarvis_dz_pending');
        if (!pendingJson) return;

        try {
            const pending = JSON.parse(pendingJson);
            const now = Date.now();
            if (now - pending.time > 30000) {
                sessionStorage.removeItem('jarvis_dz_pending');
                return;
            }
            startAutoplayPolling(pending.type, pending.id);
        } catch (e) {
            sessionStorage.removeItem('jarvis_dz_pending');
        }
    }

    // ─── GESTION DES COMMANDES ENTRANTES ──────────────────────────────────────

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
                    if (win?.dzPlayer?.play) {
                        try { win.dzPlayer.play(); } catch (e) {}
                    }
                    const audio = getAudioElement();
                    if (audio && audio.paused) {
                        try { await audio.play(); } catch (e) {}
                    }
                    const bottom = getBottomPlayer() || document;
                    const playBtn = bottom.querySelector('button[data-testid="play_button"], button[data-testid="play_button_play"], button[aria-label*="Lecture" i], button[aria-label*="Play" i]');
                    if (playBtn) {
                        robustClick(playBtn);
                    } else {
                        triggerKey('Space', ' ');
                    }
                    showToast('▶ Lecture');
                    break;
                }

                case 'pause': {
                    if (win?.dzPlayer?.pause) {
                        try { win.dzPlayer.pause(); } catch (e) {}
                    }
                    const audio = getAudioElement();
                    if (audio && !audio.paused) {
                        try { audio.pause(); } catch (e) {}
                    }
                    const bottom = getBottomPlayer() || document;
                    const pauseBtn = bottom.querySelector('button[data-testid="play_button_pause"], button[data-testid="play_button"], button[aria-label*="Pause" i]');
                    if (pauseBtn) {
                        robustClick(pauseBtn);
                    } else {
                        triggerKey('Space', ' ');
                    }
                    showToast('⏸ Pause');
                    break;
                }

                case 'toggle_play': {
                    const audio = getAudioElement();
                    const isPlaying = audio ? !audio.paused : Boolean(document.querySelector('button[data-testid="play_button_pause"], button[aria-label="Pause"], svg[data-testid="Pause"]'));

                    if (win?.dzPlayer?.playPause) {
                        try { win.dzPlayer.playPause(); } catch (e) {}
                    } else if (win?.dzPlayer?.play && win?.dzPlayer?.pause) {
                        try { isPlaying ? win.dzPlayer.pause() : win.dzPlayer.play(); } catch (e) {}
                    }

                    if (audio) {
                        try { isPlaying ? audio.pause() : audio.play(); } catch (e) {}
                    }

                    const bottom = getBottomPlayer() || document;
                    const btn = bottom.querySelector('button[data-testid="play_button_play"], button[data-testid="play_button_pause"], button[data-testid="play_button"], button[aria-label*="Lecture" i], button[aria-label*="Pause" i]');
                    if (btn) {
                        robustClick(btn);
                    } else {
                        triggerKey('Space', ' ');
                    }
                    showToast(isPlaying ? '⏸ Pause' : '▶ Lecture');
                    break;
                }

                case 'next': {
                    if (win?.dzPlayer?.control?.nextTrack) {
                        try { win.dzPlayer.control.nextTrack(); } catch (e) {}
                    } else if (win?.dzPlayer?.next) {
                        try { win.dzPlayer.next(); } catch (e) {}
                    }
                    const bottom = getBottomPlayer() || document;
                    const nextBtn = bottom.querySelector('button[data-testid="next_track_button"], button[data-testid="next_button"], button[data-testid="player-next"], button[aria-label*="suivante" i], button[aria-label*="next" i]');
                    if (nextBtn) {
                        robustClick(nextBtn);
                    } else {
                        triggerKey('ArrowRight', 'ArrowRight', true);
                    }
                    showToast('⏭ Piste suivante');
                    break;
                }

                case 'previous': {
                    if (win?.dzPlayer?.control?.prevTrack) {
                        try { win.dzPlayer.control.prevTrack(); } catch (e) {}
                    } else if (win?.dzPlayer?.prev) {
                        try { win.dzPlayer.prev(); } catch (e) {}
                    }
                    const bottom = getBottomPlayer() || document;
                    const prevBtn = bottom.querySelector('button[data-testid="previous_track_button"], button[data-testid="prev_button"], button[data-testid="player-previous"], button[aria-label*="précédente" i], button[aria-label*="previous" i]');
                    if (prevBtn) {
                        robustClick(prevBtn);
                    } else {
                        triggerKey('ArrowLeft', 'ArrowLeft', true);
                    }
                    showToast('⏮ Piste précédente');
                    break;
                }

                case 'set_shuffle': {
                    const current = isShuffleActive();
                    const target = params.enable !== undefined ? Boolean(params.enable) : !current;

                    if (win?.dzPlayer?.setShuffle) {
                        try { win.dzPlayer.setShuffle(target); } catch (e) {}
                    }

                    const bottom = getBottomPlayer() || document;
                    const shuffleBtn = bottom.querySelector('button[data-testid="shuffle_button"], button[data-testid="player-shuffle"], button[aria-label*="aléatoire" i], button[aria-label*="shuffle" i]');
                    if (shuffleBtn && current !== target) {
                        robustClick(shuffleBtn);
                    } else if (!shuffleBtn) {
                        triggerKey('KeyS', 's', true);
                    }
                    showToast(target ? '🔀 Aléatoire : Activé' : '➡️ Aléatoire : Désactivé');
                    break;
                }

                case 'set_repeat': {
                    const bottom = getBottomPlayer() || document;
                    const repeatBtn = bottom.querySelector('button[data-testid="repeat_button"], button[data-testid="player-repeat"], button[aria-label*="répéter" i], button[aria-label*="repeat" i]');
                    if (repeatBtn) {
                        robustClick(repeatBtn);
                    }
                    showToast('🔁 Répétition');
                    break;
                }

                case 'set_volume': {
                    const vol = Math.max(0, Math.min(100, parseInt(params.volume ?? 100)));
                    if (win?.dzPlayer?.setVolume) {
                        try { win.dzPlayer.setVolume(vol); } catch (e) {}
                    }
                    const audio = getAudioElement();
                    if (audio) {
                        audio.volume = vol / 100;
                    }
                    const slider = document.querySelector('input[type="range"][data-testid="volume_slider"], input[type="range"][aria-label*="volume" i], .slider-volume input[type="range"]');
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
                    if (win?.dzPlayer?.seek) {
                        try { win.dzPlayer.seek(pos); } catch (e) {}
                    }
                    if (audio) {
                        audio.currentTime = Math.max(0, Math.min(audio.duration || 9999, pos));
                    }
                    showToast(`⏱ ${Math.round(pos)}s`);
                    break;
                }

                case 'play_url': {
                    const url = params.url;
                    const itemType = params.type || '';
                    const itemId = params.id || '';

                    if (!url) {
                        success = false;
                        responseMessage = 'URL manquante.';
                        break;
                    }

                    // 1. Essai direct via dzPlayer sans recharger la page si possible
                    let playedDirectly = false;
                    if (win?.dzPlayer && itemId && !isNaN(itemId)) {
                        const numId = parseInt(itemId);
                        try {
                            if (itemType === 'playlist' && win.dzPlayer.playPlaylist) {
                                win.dzPlayer.playPlaylist(numId);
                                playedDirectly = true;
                            } else if (itemType === 'track' && win.dzPlayer.playTrack) {
                                win.dzPlayer.playTrack(numId);
                                playedDirectly = true;
                            } else if (itemType === 'album' && win.dzPlayer.playAlbum) {
                                win.dzPlayer.playAlbum(numId);
                                playedDirectly = true;
                            } else if (itemType === 'flow' && win.dzPlayer.playFlow) {
                                win.dzPlayer.playFlow();
                                playedDirectly = true;
                            }
                        } catch (e) {
                            console.warn('[J.A.R.V.I.S. Deezer] dzPlayer direct play échoué, repli DOM :', e);
                        }
                    }

                    if (playedDirectly) {
                        showToast(`▶ Lancement immédiat (${itemType})`);
                        startAutoplayPolling(itemType, itemId);
                        break;
                    }

                    // 2. Enregistrement de l'autoplay persistant
                    sessionStorage.setItem('jarvis_dz_pending', JSON.stringify({
                        url: url,
                        type: itemType,
                        id: itemId,
                        time: Date.now()
                    }));

                    const currentClean = window.location.href.split('?')[0].replace(/\/$/, '');
                    const targetClean = url.split('?')[0].replace(/\/$/, '');

                    if (currentClean === targetClean) {
                        showToast('Lancement sur la page...');
                        startAutoplayPolling(itemType, itemId);
                    } else {
                        showToast(`Chargement ${itemType || 'musique'}...`);
                        
                        try {
                            const link = document.createElement('a');
                            link.href = url;
                            link.style.display = 'none';
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                        } catch (e) {}

                        startAutoplayPolling(itemType, itemId);

                        setTimeout(() => {
                            const nowClean = window.location.href.split('?')[0].replace(/\/$/, '');
                            if (nowClean !== targetClean) {
                                window.location.href = url;
                            }
                        }, 600);
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
                console.log('✅ [J.A.R.V.I.S. Deezer] Connecté au serveur Python (ws://localhost:8765)');
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

    // ─── INITIALISATION ───────────────────────────────────────────────────────

    function init() {
        createHUD();
        dismissCookieBanner();
        connectWebSocket();
        attachAudioListeners();
        checkPendingAutoplay();
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        window.addEventListener('DOMContentLoaded', init);
        window.addEventListener('load', init);
    }

})();
