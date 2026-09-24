// ========================================================
// J.A.R.V.I.S. Client Engine - Stark Industries HUD
// ========================================================

// --- GESTION DE L'AUTHENTIFICATION & PERSISTANCE ---
const authScreen = document.getElementById('authScreen');
const mainScreen = document.getElementById('mainScreen');
const pwdInput = document.getElementById('pwdInput');
const authBtn = document.getElementById('authBtn');
const authFeedback = document.getElementById('authFeedback');

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

function setCookie(name, val, days) {
  const d = new Date();
  d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
  const secure = window.location.protocol === 'https:' ? ';Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(val)};expires=${d.toUTCString()};path=/;SameSite=Lax${secure}`;
}

function showMainUI() {
  authScreen.style.opacity = '0';
  setTimeout(() => {
    authScreen.style.display = 'none';
    mainScreen.style.display = 'flex';
  }, 400);
}

async function checkExistingAuth() {
  // 1. Vérification si accès par scan de QR code avec ticket à usage unique
  const urlParams = new URLSearchParams(window.location.search);
  const qrTicket = urlParams.get('ticket') || urlParams.get('qr');

  if (qrTicket) {
    try {
      authScreen.style.display = 'flex';
      authScreen.style.opacity = '1';
      authBtn.disabled = true;
      authBtn.innerText = "VALIDATION DU SCAN QR...";
      authFeedback.className = "feedback-success";
      authFeedback.innerText = "Scan QR détecté : enregistrement automatique du terminal...";

      const res = await fetch('/api/auth-qr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket: qrTicket })
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('jarvis_device_token', data.token);
        setCookie('jarvis_device_token', data.token, 3650);

        // Nettoyer l'URL du navigateur sans recharger la page
        const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
        window.history.replaceState({ path: cleanUrl }, '', cleanUrl);

        authFeedback.className = "feedback-success";
        authFeedback.innerText = "✦ Terminal approuvé avec succès par scan QR ! ✦";
        setTimeout(showMainUI, 600);
        return;
      } else {
        authFeedback.className = "feedback-error";
        authFeedback.innerText = "Ticket QR expiré ou invalide. Veuillez entrer le mot de passe.";
        authBtn.disabled = false;
        authBtn.innerText = "AUTORISER L'APPAREIL";
      }
    } catch (e) {
      console.error("Erreur enregistrement QR:", e);
    }
  }

  // 2. Vérification jeton existant déjà enregistré sur l'appareil
  const token = localStorage.getItem('jarvis_device_token') || getCookie('jarvis_device_token');
  if (token) {
    try {
      const res = await fetch('/api/verify?token=' + encodeURIComponent(token));
      if (res.ok) {
        const data = await res.json();
        if (data.authorized) {
          showMainUI();
          return;
        }
      }
    } catch (e) {
      console.error(e);
    }
  }
  authScreen.style.display = 'flex';
  authScreen.style.opacity = '1';
}

async function submitAuth() {
  const pwd = pwdInput.value.trim();
  if (!pwd) {
    authFeedback.className = "feedback-error";
    authFeedback.innerText = "Veuillez entrer le mot de passe.";
    return;
  }

  authBtn.disabled = true;
  authBtn.innerText = "AUTHENTIFICATION...";
  authFeedback.innerText = "";

  try {
    const res = await fetch('/api/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    });

    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('jarvis_device_token', data.token);
      setCookie('jarvis_device_token', data.token, 3650);

      authFeedback.className = "feedback-success";
      authFeedback.innerText = "Appareil approuvé et enregistré !";
      setTimeout(showMainUI, 500);
    } else {
      authFeedback.className = "feedback-error";
      authFeedback.innerText = "Mot de passe incorrect. Accès refusé.";
      authBtn.disabled = false;
      authBtn.innerText = "AUTORISER L'APPAREIL";
      pwdInput.value = "";
      pwdInput.focus();
    }
  } catch (err) {
    authFeedback.className = "feedback-error";
    authFeedback.innerText = "Erreur réseau avec le serveur.";
    authBtn.disabled = false;
    authBtn.innerText = "AUTORISER L'APPAREIL";
  }
}

authBtn.onclick = submitAuth;
pwdInput.onkeydown = (e) => {
  if (e.key === 'Enter') submitAuth();
};

checkExistingAuth();

// --- VARIABLES UI & AUDIO ---
const btn = document.getElementById('toggleBtn');
const btnLabel = document.getElementById('btnLabel');
const reactorHalo = document.getElementById('reactorHalo');
const stateBadge = document.getElementById('stateBadge');
const stateLabel = document.getElementById('stateLabel');
const statusMessage = document.getElementById('statusMessage');
const micDot = document.getElementById('micDot');
const micText = document.getElementById('micText');
const micDb = document.getElementById('micDb');
const micBars = document.querySelectorAll('.eq-bar');
const transcriptBox = document.getElementById('transcriptBox');
const volumeSlider = document.getElementById('volumeSlider');
const volPercent = document.getElementById('volPercent');
const muteBtn = document.getElementById('muteBtn');
const volIcon = document.getElementById('volIcon');
const engineChip = document.getElementById('engineChip');
const engineSourceBadge = document.getElementById('engineSourceBadge');
const engineModelText = document.getElementById('engineModelText');
const engineKeyBadge = document.getElementById('engineKeyBadge');
const engineActionsBadge = document.getElementById('engineActionsBadge');
const engineActionsCount = document.getElementById('engineActionsCount');
const btnOpenOverview = document.getElementById('btnOpenOverview');
const supervisionActionBadge = document.getElementById('supervisionActionBadge');

// --- MODAL SUPERVISION GLOBALE (MODÈLES, CLÉS API, ACTIONS & FENÊTRES) ---
const supervisionModal = document.getElementById('supervisionModal');
const btnCloseSupervision = document.getElementById('btnCloseSupervision');
const btnCloseSupervisionFooter = document.getElementById('btnCloseSupervisionFooter');
const btnRefreshSupervision = document.getElementById('btnRefreshSupervision');
const supVoiceStatusTag = document.getElementById('supVoiceStatusTag');
const supVoiceModel = document.getElementById('supVoiceModel');
const supVoiceDetail = document.getElementById('supVoiceDetail');
const supVoiceKeyPill = document.getElementById('supVoiceKeyPill');
const supVoiceCost = document.getElementById('supVoiceCost');
const supVoiceKeyMasked = document.getElementById('supVoiceKeyMasked');
const btnSwitchLiveStd = document.getElementById('btnSwitchLiveStd');
const btnSwitchLiveThinking = document.getElementById('btnSwitchLiveThinking');
const supActionsCountBadge = document.getElementById('supActionsCountBadge');
const supActiveActionsContainer = document.getElementById('supActiveActionsContainer');
const supNoActiveActions = document.getElementById('supNoActiveActions');
const supToolsTable = document.getElementById('supToolsTable');
const supWindowsCountBadge = document.getElementById('supWindowsCountBadge');
const supWindowsList = document.getElementById('supWindowsList');
const supSummaryFreeKey = document.getElementById('supSummaryFreeKey');
const supSummaryPaidBadge = document.getElementById('supSummaryPaidBadge');
const supSummaryPaidKey = document.getElementById('supSummaryPaidKey');

// Panneau & Modal Navigateur
const browserDock = document.getElementById('browserDock');
const browserDockTitle = document.getElementById('browserDockTitle');
const btnViewBrowser = document.getElementById('btnViewBrowser');
const btnOpenBrowser = document.getElementById('btnOpenBrowser');
const browserModal = document.getElementById('browserModal');
const btnCloseBrowserModal = document.getElementById('btnCloseBrowserModal');
const btnModalOpenExternal = document.getElementById('btnModalOpenExternal');
const browserScreenshotImg = document.getElementById('browserScreenshotImg');
const modalBrowserTitle = document.getElementById('modalBrowserTitle');

// Panneau Tâche Active (Antigravity IDE)
const taskDock = document.getElementById('taskDock');
const taskDockStatus = document.getElementById('taskDockStatus');
const taskDockModel = document.getElementById('taskDockModel');
const taskDockInstruction = document.getElementById('taskDockInstruction');
const taskDockProgressText = document.getElementById('taskDockProgressText');
const taskDirectiveInput = document.getElementById('taskDirectiveInput');
const btnSendDirective = document.getElementById('btnSendDirective');

// Panneau Notification E-mail
const emailDock = document.getElementById('emailDock');
const emailDockStatus = document.getElementById('emailDockStatus');
const emailDockSubject = document.getElementById('emailDockSubject');
const emailDockRecipient = document.getElementById('emailDockRecipient');
let emailDockTimer = null;

// Modal Autorisation Clé Payante Stark
const paidConsentModal = document.getElementById('paidConsentModal');
const paidConsentTitle = document.getElementById('paidConsentTitle');
const paidConsentReason = document.getElementById('paidConsentReason');
const paidConsentCost = document.getElementById('paidConsentCost');
const paidConsentMessage = document.getElementById('paidConsentMessage');
const btnApprovePaid = document.getElementById('btnApprovePaid');
const btnRejectPaid = document.getElementById('btnRejectPaid');
let pendingPaidAction = "general";

function showPaidConsentModal(data) {
  pendingPaidAction = data.action || "general";
  if (paidConsentTitle) paidConsentTitle.innerText = data.title || "AUTORISATION CLÉ PAYANTE REQUISE";
  if (paidConsentReason) paidConsentReason.innerText = data.reason || "Mobilisation de l'API payante";
  if (paidConsentCost) paidConsentCost.innerText = data.estimated_cost || "~0.005 $";
  if (paidConsentMessage) paidConsentMessage.innerText = data.message || "Votre accord est requis pour utiliser l'API payante.";
  if (paidConsentModal) paidConsentModal.style.display = 'flex';
  playActionChime();
}

function hidePaidConsentModal() {
  if (paidConsentModal) paidConsentModal.style.display = 'none';
}

if (btnApprovePaid) {
  btnApprovePaid.addEventListener('click', () => {
    hidePaidConsentModal();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'paid_consent_response',
        action: pendingPaidAction,
        approved: true
      }));
    }
  });
}

if (btnRejectPaid) {
  btnRejectPaid.addEventListener('click', () => {
    hidePaidConsentModal();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'paid_consent_response',
        action: pendingPaidAction,
        approved: false
      }));
    }
  });
}

let currentWebUrl = "https://www.google.com";
let currentWebTitle = "Page Web";

let ws = null;
let audioCtx = null;
let dynamicsCompressor = null;
let masterGainNode = null;
let mediaStream = null;
let processor = null;
let analyser = null;
let inputNode = null;
let isConnected = false;
let isConnecting = false;
let nextPlayTime = 0;
let micAnimFrame = null;
let scheduledAudioSources = [];
let isJarvisSpeaking = false;
let isToolExecuting = false;   // Vrai pendant l'exécution d'un outil (browser, code, email...)
let turnCompletePending = false;
let speechEndTimer = null;
let silenceSenderInterval = null; // Maintient la session Gemini vivante pendant les actions
let currentRole = null;
let currentEntryEl = null;

let speakerAnalyser = null;
let speakerDataArray = null;

// Éléments de l'avatar féminin interactif
const avatarLipLower = document.querySelector('.avatar-lip-lower');
const avatarMouthCavity = document.querySelector('.avatar-mouth-cavity');
const earLeds = document.querySelectorAll('.ear-led');

function animateAvatarSpeech(volume) {
  const now = performance.now();
  let openAmount = 0;
  if (volume > 4) {
    // Synchronisation en temps réel selon les fréquences de voix renvoyées
    openAmount = Math.min(5.5, (volume / 255) * 8.0);
  } else if (isJarvisSpeaking) {
    // Oscillations phonétiques naturelles lorsque le flux vocal de Jarvis est actif
    openAmount = (Math.sin(now * 0.02) * 0.5 + 0.5) * 3.6 + (Math.sin(now * 0.045) * 0.25) * 1.5;
  }
  if (avatarLipLower) {
    avatarLipLower.style.transform = `translateY(${openAmount.toFixed(1)}px)`;
  }
  if (avatarMouthCavity) {
    avatarMouthCavity.setAttribute('ry', (1.2 + openAmount * 0.5).toFixed(1));
  }
}

const btnInterrupt = document.getElementById('btnInterrupt');
if (btnInterrupt) {
  btnInterrupt.onclick = () => {
    interruptPlayback();
    setJarvisState('listening', "JARVIS à l'écoute, posez votre question...");
  };
}

// --- GESTION DU VOLUME MAÎTRE & PERSISTANCE ---
let currentVolume = parseFloat(localStorage.getItem('jarvis_volume') || '0.85');
let isMuted = false;
let previousVolume = currentVolume;

function updateVolIcon() {
  if (isMuted || currentVolume === 0) {
    volIcon.innerHTML = '<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>';
    volIcon.style.fill = '#f87171';
  } else {
    volIcon.innerHTML = '<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>';
    volIcon.style.fill = '#38bdf8';
  }
}

function applyVolume(vol) {
  currentVolume = Math.max(0, Math.min(1, vol));
  if (masterGainNode && audioCtx) {
    masterGainNode.gain.setTargetAtTime(currentVolume, audioCtx.currentTime, 0.03);
  }
  localStorage.setItem('jarvis_volume', currentVolume.toString());
  const p = Math.round(currentVolume * 100);
  volumeSlider.value = p;
  volPercent.innerText = `${p}%`;
  updateVolIcon();
}

volumeSlider.oninput = (e) => {
  isMuted = false;
  applyVolume(parseFloat(e.target.value) / 100);
};

muteBtn.onclick = () => {
  if (isMuted) {
    isMuted = false;
    applyVolume(previousVolume > 0 ? previousVolume : 0.85);
  } else {
    previousVolume = currentVolume;
    isMuted = true;
    applyVolume(0);
  }
};

applyVolume(currentVolume);

// --- GESTION DES ÉTATS JARVIS & DU MODÈLE ACTIF ---
function setJarvisState(state, customMsg, detail, engineInfo) {
  btn.classList.remove('state-listening', 'state-thinking', 'state-speaking', 'state-coding', 'state-browsing', 'state-emailing', 'state-offline');
  stateBadge.className = 'state-badge';

  // Mise à jour de la couleur d'ambiance du halo selon la tâche en cours
  if (reactorHalo) {
    if (state === 'speaking') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(0, 240, 255, 0.35) 0%, transparent 70%)';
    } else if (state === 'coding') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(168, 85, 247, 0.35) 0%, transparent 70%)';
    } else if (state === 'browsing') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(56, 189, 248, 0.35) 0%, transparent 70%)';
    } else if (state === 'thinking') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(245, 158, 11, 0.35) 0%, transparent 70%)';
    } else if (state === 'emailing') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(16, 185, 129, 0.35) 0%, transparent 70%)';
    } else if (state === 'listening') {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(56, 189, 248, 0.28) 0%, transparent 70%)';
    } else {
      reactorHalo.style.background = 'radial-gradient(circle, rgba(100, 116, 139, 0.18) 0%, transparent 70%)';
    }
  }

  // Mise à jour de la puce Moteur, Modèle & Clé API
  let isPaidKey = false;
  if (engineInfo && engineInfo.engine) {
    const isAntigravity = engineInfo.engine.toLowerCase().includes("antigravity");
    isPaidKey = (engineInfo.key_type === 'paid') || isAntigravity;
    if (engineSourceBadge) {
      engineSourceBadge.className = `engine-badge ${isAntigravity ? 'badge-antigravity' : 'badge-google'}`;
      engineSourceBadge.innerText = engineInfo.engine.toUpperCase();
    }
    if (engineModelText) {
      engineModelText.innerText = (engineInfo.model || (isAntigravity ? "Antigravity Agent" : "Gemini")).toUpperCase();
    }
  } else if (state === 'offline') {
    if (engineSourceBadge) {
      engineSourceBadge.className = 'engine-badge badge-google';
      engineSourceBadge.innerText = 'SYSTÈME VEILLE';
    }
    if (engineModelText) {
      engineModelText.innerText = 'HORS LIGNE';
    }
  } else if (state === 'listening' || state === 'speaking') {
    if (engineSourceBadge) {
      engineSourceBadge.className = 'engine-badge badge-google';
      engineSourceBadge.innerText = 'GOOGLE API';
    }
    if (engineModelText) {
      engineModelText.innerText = (window._currentLiveModelName || 'GEMINI 3.8 LIVE').toUpperCase();
    }
  }

  if (engineKeyBadge) {
    if (isPaidKey) {
      engineKeyBadge.className = 'engine-key-badge badge-key-paid';
      engineKeyBadge.innerText = 'CLÉ PAYANTE';
      engineKeyBadge.title = 'Mobilise la clé API Payante (avec accord préalable)';
    } else {
      engineKeyBadge.className = 'engine-key-badge badge-key-free';
      engineKeyBadge.innerText = 'CLÉ GRATUITE';
      engineKeyBadge.title = 'Fonctionne sur la clé API Gratuite Google (0.00$)';
    }
  }

  if (state === 'speaking') {
    btn.classList.add('state-speaking');
    stateBadge.classList.add('badge-speaking');
    stateLabel.innerText = "PAROLE";
    statusMessage.innerText = customMsg || "JARVIS vous répond...";
    btnLabel.innerText = "COUPER";
    if (btnInterrupt) btnInterrupt.style.display = 'inline-flex';
  } else {
    if (btnInterrupt && !isJarvisSpeaking) {
      btnInterrupt.style.display = 'none';
    }
    if (state === 'listening') {
      btn.classList.add('state-listening');
      stateBadge.classList.add('badge-listening');
      stateLabel.innerText = "À L'ÉCOUTE";
      statusMessage.innerText = customMsg || "Parlez naturellement, JARVIS vous écoute...";
      btnLabel.innerText = "ONLINE";
    } else if (state === 'thinking') {
      btn.classList.add('state-thinking');
      stateBadge.classList.add('badge-thinking');
      stateLabel.innerText = "RÉFLEXION";
      statusMessage.innerText = customMsg || "JARVIS analyse votre demande...";
      btnLabel.innerText = "ONLINE";
    } else if (state === 'coding') {
      btn.classList.add('state-coding');
      stateBadge.classList.add('badge-coding');
      stateLabel.innerText = "PROGRAMMATION";
      statusMessage.innerText = customMsg || (detail ? `Exécution : ${detail}` : "JARVIS modifie le projet (Antigravity)...");
      btnLabel.innerText = "ONLINE";
    } else if (state === 'browsing') {
      btn.classList.add('state-browsing');
      stateBadge.classList.add('badge-browsing');
      stateLabel.innerText = "NAVIGATION SUR INTERNET";
      statusMessage.innerText = customMsg || (detail ? `Navigation : ${detail}` : "JARVIS navigue sur Internet...");
      browserDock.style.display = 'flex';
      btnLabel.innerText = "ONLINE";
    } else if (state === 'emailing') {
      btn.classList.add('state-emailing');
      stateBadge.classList.add('badge-emailing');
      stateLabel.innerText = "EXPÉDITION D'E-MAIL";
      statusMessage.innerText = customMsg || (detail ? `E-mail : ${detail}` : "Préparation et envoi du courriel...");
      btnLabel.innerText = "ONLINE";
    } else {
      btn.classList.add('state-offline');
      stateBadge.classList.add('badge-offline');
      stateLabel.innerText = "HORS LIGNE";
      statusMessage.innerText = customMsg || "Touchez JARVIS pour activer l'assistance";
      btnLabel.innerText = "CONNECT";
      if (btnInterrupt) btnInterrupt.style.display = 'none';
    }
  }
}

// Gestion propre et consolidée des bulles de transcription
function handleTranscript(role, text, mode) {
  if (!text || !text.trim()) return;

  const welcome = document.getElementById('welcomeMsg');
  if (welcome) welcome.remove();

  if (role === 'user') {
    const incoming = text.trim();

    if (currentRole !== 'user' || !currentEntryEl) {
      currentRole = 'user';
      currentEntryEl = document.createElement('div');
      currentEntryEl.className = 'transcript-entry transcript-user';
      currentEntryEl.innerHTML = `<span class="transcript-label" style="color:#38bdf8;">VOUS:</span> <span class="transcript-body"></span>`;
      transcriptBox.appendChild(currentEntryEl);
    }

    const body = currentEntryEl.querySelector('.transcript-body');
    if (body) {
      body.innerText = incoming;
    }
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
    return;
  }

  // Dès que Jarvis ou une action prend la parole, clore le bloc utilisateur
  finalizeUserSpeech();

  if (role !== currentRole || !currentEntryEl) {
    currentRole = role;
    currentEntryEl = document.createElement('div');
    currentEntryEl.className = `transcript-entry transcript-${role}`;
    
    const label = role === 'jarvis' ? 'JARVIS:' : 'ACTION:';
    const color = role === 'jarvis' ? '#f0f9ff' : '#c084fc';
    currentEntryEl.innerHTML = `<span class="transcript-label" style="color:${color};">${label}</span> <span class="transcript-body"></span>`;
    transcriptBox.appendChild(currentEntryEl);
  }

  const body = currentEntryEl.querySelector('.transcript-body');
  if (body) {
    if (role === 'jarvis') {
      if (mode === 'replace') {
        body.innerText = text.trim();
      } else {
        body.innerText += text;
      }
    } else {
      // Action / tool
      body.innerText = text.trim();
    }
  }
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

// Accusé de réception sonore futuriste Stark HUD
function playActionChime() {
  if (!audioCtx) return;
  try {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    const now = audioCtx.currentTime;
    osc.frequency.setValueAtTime(587.33, now);
    osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc.connect(gain);
    gain.connect(masterGainNode || audioCtx.destination);
    osc.start(now);
    osc.stop(now + 0.25);
  } catch (e) {
    console.warn("[HUD] Erreur son chime:", e);
  }
}

function finalizeUserSpeech() {
  currentRole = null;
  currentEntryEl = null;
}

function resetTranscriptTurn() {
  finalizeUserSpeech();
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

// Rééchantillonnage 16 kHz rapide
function downsampleTo16k(inputBuffer, inSampleRate) {
  if (inSampleRate === 16000) return inputBuffer;
  const ratio = inSampleRate / 16000;
  const newLen = Math.round(inputBuffer.length / ratio);
  const result = new Float32Array(newLen);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let sum = 0, count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < inputBuffer.length; i++) {
      sum += inputBuffer[i];
      count++;
    }
    result[offsetResult] = count > 0 ? (sum / count) : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

// Interruption : coupe immédiatement le son en cours
function interruptPlayback() {
  if (speechEndTimer) {
    clearTimeout(speechEndTimer);
    speechEndTimer = null;
  }
  turnCompletePending = false;
  scheduledAudioSources.forEach(s => {
    try { s.stop(); } catch (e) {}
  });
  scheduledAudioSources = [];
  isJarvisSpeaking = false;
  if (btnInterrupt) btnInterrupt.style.display = 'none';
  if (audioCtx) {
    nextPlayTime = audioCtx.currentTime;
  }
  resetTranscriptTurn();
  if (isConnected) {
    btnLabel.innerText = "ONLINE";
  }
}

// --- ÉCOUTE VOCALE CONTINUE & GUIDAGE EN DIRECT (STARK LIVE SPEECH ENGINE) ---
// Capte en temps réel les consignes orales de l'utilisateur pendant le développement
let liveSpeechRecognizer = null;
let isRecognizerRunning = false;

function startLiveSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.warn("[STT] Reconnaissance vocale continue non supportée sur ce navigateur.");
    return;
  }

  if (liveSpeechRecognizer) {
    try { liveSpeechRecognizer.abort(); } catch (e) {}
    liveSpeechRecognizer = null;
  }

  try {
    const recognizer = new SpeechRecognition();
    recognizer.lang = 'fr-FR';
    recognizer.continuous = true;
    recognizer.interimResults = true;
    recognizer.maxAlternatives = 1;

    recognizer.onstart = () => {
      isRecognizerRunning = true;
      console.log("[STT] Écoute vocale active pour consignes et interaction.");
    };

    recognizer.onresult = (event) => {
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }

      const text = finalTranscript.trim();
      if (!text) return;

      // Si JARVIS est en cours de développement (panneau taskDock actif)
      if (taskDock && taskDock.style.display === 'flex') {
        console.log("[STT] Consigne vocale captée pendant le codage :", text);
        
        // 1. Inscrire la parole de l'utilisateur dans l'historique
        handleTranscript('user', text, 'append');
        
        // 2. Mettre à jour visuellement le dock de développement
        if (taskDockInstruction) {
          taskDockInstruction.innerText = "Consigne prise en compte : " + text;
        }
        if (taskDockProgressText) {
          taskDockProgressText.innerText = "J'adapte le code selon votre consigne...";
        }
        
        // 3. Chime sonore subtil Stark
        playActionChime();
        
        // 4. Transmission temps réel à Antigravity
        sendLiveDirective(text);
      }
    };

    recognizer.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        console.warn("[STT] Notice SpeechRecognition:", e.error);
      }
    };

    recognizer.onend = () => {
      isRecognizerRunning = false;
      if (isConnected) {
        setTimeout(() => {
          if (isConnected && !isRecognizerRunning && liveSpeechRecognizer === recognizer) {
            try { recognizer.start(); } catch (err) {}
          }
        }, 300);
      }
    };

    liveSpeechRecognizer = recognizer;
    recognizer.start();
  } catch (err) {
    console.error("[STT] Erreur lancement SpeechRecognition:", err);
  }
}

function stopLiveSpeechRecognition() {
  if (liveSpeechRecognizer) {
    try {
      liveSpeechRecognizer.abort();
    } catch (e) {}
    liveSpeechRecognizer = null;
  }
  isRecognizerRunning = false;
}

// Lecture fluide des trames audio PCM 24kHz renvoyées par Gemini à travers DynamicsCompressor & MasterGain
function playPcmChunk(arrayBuffer) {
  if (!audioCtx || !masterGainNode) return;
  const int16 = new Int16Array(arrayBuffer);
  if (int16.length === 0) return;

  // Résumé de la session si l'AudioContext a été suspendu (ex: onglet en arrière-plan)
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }

  const audioBuffer = audioCtx.createBuffer(1, float32.length, 24000);
  audioBuffer.getChannelData(0).set(float32);

  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(dynamicsCompressor || masterGainNode);

  const now = audioCtx.currentTime;
  if (speechEndTimer) {
    clearTimeout(speechEndTimer);
    speechEndTimer = null;
  }

  if (!isJarvisSpeaking) {
    isJarvisSpeaking = true;
    isToolExecuting = false; // Dès que Jarvis commence à parler, l'exécution de l'outil est terminée
    stopSilenceSender();     // Arrêt du silence de maintien de session
    setJarvisState('speaking', "JARVIS vous répond...");
    btnLabel.innerText = "COUPER";
    if (btnInterrupt) btnInterrupt.style.display = 'inline-flex';
  }

  // Jitter buffer : lookahead de 150ms pour absorber les variations réseau sans latence perceptible
  if (nextPlayTime < now) {
    nextPlayTime = now + 0.15;
  }
  source.start(nextPlayTime);
  nextPlayTime += audioBuffer.duration;

  scheduledAudioSources.push(source);
  source.onended = () => {
    const idx = scheduledAudioSources.indexOf(source);
    if (idx !== -1) scheduledAudioSources.splice(idx, 1);
    checkSpeechEnded();
  };
}

// Vérifie si la restitution audio de Jarvis est réellement terminée dans les haut-parleurs
function checkSpeechEnded() {
  if (scheduledAudioSources.length === 0 && turnCompletePending) {
    if (speechEndTimer) clearTimeout(speechEndTimer);
    // Délai de garde acoustique (400ms) pour absorber la réverbération et les fins de phrase
    speechEndTimer = setTimeout(() => {
      if (scheduledAudioSources.length === 0 && turnCompletePending) {
        turnCompletePending = false;
        isJarvisSpeaking = false;
        btnLabel.innerText = "ONLINE";
        if (btnInterrupt) btnInterrupt.style.display = 'none';
        finalizeUserSpeech();
        resetTranscriptTurn();
        if (taskDock && taskDock.style.display === 'flex') {
          setJarvisState('coding', "JARVIS développe via Antigravity...");
        } else {
          setJarvisState('listening', "JARVIS à l'écoute, posez votre question...");
        }
      }
    }, 400);
  }
}

// -----------------------------------------------------------------------
// SILENCE SENDER : maintient la session Gemini Live vivante pendant
// l'exécution des outils (browser, code, email...) en envoyant des trames
// de silence 16kHz, empêchant toute déconnexion ou instabilité de session.
// -----------------------------------------------------------------------
const SILENCE_FRAME_SIZE = 1600; // 100ms de silence à 16kHz
const SILENCE_BUFFER = new Int16Array(SILENCE_FRAME_SIZE); // rempli de zéros

function startSilenceSender() {
  if (silenceSenderInterval) return; // Déjà actif
  silenceSenderInterval = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN && isToolExecuting) {
      ws.send(SILENCE_BUFFER.buffer);
    } else if (!isToolExecuting) {
      stopSilenceSender();
    }
  }, 100); // Toutes les 100ms
}

function stopSilenceSender() {
  if (silenceSenderInterval) {
    clearInterval(silenceSenderInterval);
    silenceSenderInterval = null;
  }
}

// Boucle d'analyse audio du microphone (VU-mètre réactif & dB réels en direct)
let bargeInConsecutiveFrames = 0;
function startMicMonitoring() {
  if (!analyser) return;
  const dataArray = new Uint8Array(analyser.frequencyBinCount);

  function updateMic() {
    if (!analyser) return;
    micAnimFrame = requestAnimationFrame(updateMic);

    analyser.getByteFrequencyData(dataArray);

    let sum = 0;
    let peak = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const val = dataArray[i];
      sum += val;
      if (val > peak) peak = val;
    }
    const avg = sum / dataArray.length;
    const volumePercent = Math.min(100, Math.round((avg / 128) * 100));
    const approxDb = peak > 1 ? Math.round(20 * Math.log10(peak / 255)) : -60;

    // Mise à jour visuelle des 9 barres d'égaliseur
    const step = Math.floor(dataArray.length / micBars.length);
    for (let i = 0; i < micBars.length; i++) {
      const val = dataArray[i * step] || 0;
      const h = Math.max(4, Math.round((val / 255) * 16));
      micBars[i].style.height = `${h}px`;
      if (val > 25) {
        micBars[i].style.background = '#38bdf8';
        micBars[i].style.boxShadow = '0 0 8px #38bdf8';
      } else {
        micBars[i].style.background = '#0f172a';
        micBars[i].style.boxShadow = 'none';
      }
    }

    // Protection et Barge-in vocal intelligent :
    // On ne coupe la parole QUE si l'utilisateur parle délibérément très fort (> 75%)
    // directement dans le micro pendant plusieurs trames d'affilée (~200ms).
    // Le son des haut-parleurs ne déclenchera JAMAIS d'interruption accidentelle !
    if (isJarvisSpeaking || scheduledAudioSources.length > 0) {
      if (volumePercent > 75) {
        bargeInConsecutiveFrames++;
        if (bargeInConsecutiveFrames >= 8) {
          interruptPlayback();
          setJarvisState('listening', "À l'écoute, posez votre question...");
          bargeInConsecutiveFrames = 0;
        }
      } else {
        bargeInConsecutiveFrames = 0;
      }
    } else {
      bargeInConsecutiveFrames = 0;
    }

    // Réaction du halo et du texte du micro
    if (isJarvisSpeaking || scheduledAudioSources.length > 0) {
      // Lecture du volume restitué par Jarvis pour animer les lèvres
      let speakVol = 0;
      if (speakerAnalyser && speakerDataArray) {
        speakerAnalyser.getByteFrequencyData(speakerDataArray);
        let sum = 0;
        for (let i = 0; i < speakerDataArray.length; i++) sum += speakerDataArray[i];
        speakVol = sum / speakerDataArray.length;
      }
      animateAvatarSpeech(speakVol);

      // Visualisation dynamique pendant la prise de parole de Jarvis
      reactorHalo.style.transform = `scale(${1.04 + (volumePercent / 300)})`;
      reactorHalo.style.opacity = '0.6';
      micDot.style.background = '#38bdf8';
      micDot.style.boxShadow = '0 0 8px #38bdf8';
      micText.innerText = "JARVIS S'EXPRIME (MICRO PROTÉGÉ)";
      micText.style.color = '#38bdf8';
      micDb.innerText = approxDb > -58 ? `${approxDb} dB` : "- INF dB";
      micDb.style.color = '#38bdf8';
    } else {
      animateAvatarSpeech(0);
      if (volumePercent > 5) {
        const scale = 1 + (volumePercent / 200);
        reactorHalo.style.transform = `scale(${scale})`;
        reactorHalo.style.opacity = `${0.3 + (volumePercent / 120)}`;
        micDot.style.background = '#10b981';
        micDot.style.boxShadow = '0 0 8px #10b981';
        micText.innerText = `VOIX DÉTECTÉE (${volumePercent}%)`;
        micText.style.color = '#38bdf8';
        micDb.innerText = `${approxDb} dB`;
        micDb.style.color = '#10b981';

        // Illumination dynamique des récepteurs auditifs de l'avatar
        if (earLeds && earLeds.length > 0) {
          const glowPx = Math.min(10, 3 + (volumePercent / 10));
          earLeds.forEach(led => {
            led.style.filter = `drop-shadow(0 0 ${glowPx}px #38bdf8)`;
            led.style.fill = '#38bdf8';
          });
        }
      } else {
        reactorHalo.style.transform = 'scale(1)';
        reactorHalo.style.opacity = '0.2';
        micDot.style.background = '#0284c7';
        micDot.style.boxShadow = 'none';
        micText.innerText = "MICRO ACTIF (SILENCE)";
        micText.style.color = '#64748b';
        micDb.innerText = approxDb > -58 ? `${approxDb} dB` : "- INF dB";
        micDb.style.color = '#64748b';

        if (earLeds && earLeds.length > 0) {
          earLeds.forEach(led => {
            led.style.filter = 'none';
            led.style.fill = '#0284c7';
          });
        }
      }
    }
  }

  if (micAnimFrame) cancelAnimationFrame(micAnimFrame);
  micAnimFrame = requestAnimationFrame(updateMic);
}

async function startJarvis() {
  if (isConnecting || isConnected || (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN))) {
    console.warn("[WebSocket] Connexion déjà en cours ou active. Annulation de la double demande.");
    return;
  }
  isConnecting = true;

  // Nettoyage strict préalable pour garantir une seule instance WebSocket et ressources audio uniques
  if (ws) {
    try {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      ws.close();
    } catch (e) {}
    ws = null;
  }
  if (processor) {
    try { processor.disconnect(); } catch (e) {}
    processor = null;
  }
  if (mediaStream) {
    try { mediaStream.getTracks().forEach(t => t.stop()); } catch (e) {}
    mediaStream = null;
  }
  if (audioCtx) {
    try { audioCtx.close(); } catch (e) {}
    audioCtx = null;
  }

  try {
    statusMessage.innerText = "Initialisation du microphone...";
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AudioContextClass();
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }

    // Dynamics Compressor pour maintenir un volume sonore constant et empêcher tout pic ou baisse inopinée
    dynamicsCompressor = audioCtx.createDynamicsCompressor();
    dynamicsCompressor.threshold.setValueAtTime(-18, audioCtx.currentTime);
    dynamicsCompressor.knee.setValueAtTime(12, audioCtx.currentTime);
    dynamicsCompressor.ratio.setValueAtTime(6, audioCtx.currentTime);
    dynamicsCompressor.attack.setValueAtTime(0.001, audioCtx.currentTime); // Attaque ultra-rapide pour éviter les pops
    dynamicsCompressor.release.setValueAtTime(0.15, audioCtx.currentTime); // Release rapide pour transitions fluides

    // GainNode Maître pour contrôle direct du volume
    masterGainNode = audioCtx.createGain();
    masterGainNode.gain.value = isMuted ? 0 : currentVolume;

    // Chaîne audio : Source -> DynamicsCompressor -> MasterGain -> Destination
    dynamicsCompressor.connect(masterGainNode);
    masterGainNode.connect(audioCtx.destination);

    // Analyseur de sortie pour le mouvement des lèvres de l'avatar (lip-sync vocal)
    try {
      speakerAnalyser = audioCtx.createAnalyser();
      speakerAnalyser.fftSize = 64;
      masterGainNode.connect(speakerAnalyser);
      speakerDataArray = new Uint8Array(speakerAnalyser.frequencyBinCount);
    } catch (e) {
      console.warn("Échec init speakerAnalyser:", e);
    }

    // Configuration MediaSession pour synchronisation mobile OS
    if ('mediaSession' in navigator) {
      try {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: 'J.A.R.V.I.S. Voice Stream',
          artist: 'Stark Industries',
          album: 'Stark AI Core'
        });
        navigator.mediaSession.setActionHandler('pause', () => interruptPlayback());
        navigator.mediaSession.setActionHandler('stop', () => interruptPlayback());
      } catch (e) {}
    }

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false, // Ne pas laisser Windows moduler le volume tout seul !
        channelCount: 1
      }
    });

    window._jarvisStream = mediaStream;
    window._jarvisCtx = audioCtx;

    const token = localStorage.getItem('jarvis_device_token') || getCookie('jarvis_device_token') || '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      isConnecting = false;
      isConnected = true;
      btn.classList.add('active');
      btnLabel.innerText = "ONLINE";
      setJarvisState('listening', "Canal vocal connecté, initialisation...");
      resetTranscriptTurn();
      startLiveSpeechRecognition();
    };

    inputNode = audioCtx.createMediaStreamSource(mediaStream);
    window._jarvisInput = inputNode;

    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    inputNode.connect(analyser);

    // Buffer plus grand (4096) pour réduire les glitches du ScriptProcessor
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    window._jarvisProcessor = processor;

    processor.onaudioprocess = (e) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        if (audioCtx.state === 'suspended') {
          audioCtx.resume();
        }

        // Gating acoustique étendu :
        // - Pendant que Jarvis parle : évite l'auto-interruption (echo)
        // - Pendant l'exécution d'un outil : le silence est envoyé séparément par startSilenceSender()
        if (isJarvisSpeaking || scheduledAudioSources.length > 0 || isToolExecuting) {
          return;
        }

        const rawFloat32 = e.inputBuffer.getChannelData(0);
        const resampled = downsampleTo16k(rawFloat32, audioCtx.sampleRate);
        const int16 = new Int16Array(resampled.length);
        for (let i = 0; i < resampled.length; i++) {
          int16[i] = Math.max(-1, Math.min(1, resampled[i])) * 0x7FFF;
        }
        ws.send(int16.buffer);
      }
    };

    analyser.connect(processor);

    const muteNode = audioCtx.createGain();
    muteNode.gain.value = 0.0000001;
    processor.connect(muteNode);
    muteNode.connect(audioCtx.destination);

    // VU-mètre actif dès l'ouverture
    startMicMonitoring();

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'status') {
            setJarvisState(msg.state, msg.msg, msg.detail || msg.task, { engine: msg.engine, model: msg.model });
            if (msg.state === 'coding') {
              if (taskDock) taskDock.style.display = 'flex';
              if (taskDockStatus) taskDockStatus.innerText = "DÉVELOPPEMENT EN COURS";
              if (taskDockInstruction) taskDockInstruction.innerText = msg.task || msg.detail || "Développement du projet...";
              if (taskDockModel) taskDockModel.innerText = msg.model || "Antigravity IDE";
              // Activation du gating + silence sender pour maintien de session pendant le codage
              isToolExecuting = true;
              startSilenceSender();
            } else if (msg.state === 'browsing' || msg.state === 'emailing' || msg.state === 'thinking') {
              // Gating mic + silence sender pendant toutes les actions Jarvis
              isToolExecuting = true;
              startSilenceSender();
            }
          } else if (msg.type === 'jarvis_announcement') {
            handleTranscript('jarvis', msg.text, 'replace');
            playActionChime();
          } else if (msg.type === 'task_progress_oral') {
            if (taskDock) {
              taskDock.style.display = 'flex';
              if (taskDockProgressText) taskDockProgressText.innerText = msg.text;
            }
            handleTranscript('jarvis', msg.text, 'append');
          } else if (msg.type === 'task_completed') {
            isToolExecuting = false;
            stopSilenceSender();
            if (msg.is_error || msg.status === 'error') {
              if (taskDockStatus) {
                taskDockStatus.innerText = msg.error_type === 'high_demand' ? "SERVEURS SATURÉS (503)" : "ARRÊT DU DÉVELOPPEMENT";
                taskDockStatus.style.color = "#f87171";
              }
              if (taskDockProgressText) {
                taskDockProgressText.innerText = msg.summary || "Forte demande sur les modèles Antigravity.";
              }
              if (taskDock) taskDock.style.borderColor = "rgba(239, 68, 68, 0.6)";
              setTimeout(() => {
                if (taskDock) taskDock.style.display = 'none';
                if (taskDock) taskDock.style.borderColor = '';
                if (taskDockStatus) taskDockStatus.style.color = '';
              }, 6000);
            } else {
              if (taskDockStatus) {
                taskDockStatus.innerText = "DÉVELOPPEMENT TERMINÉ";
                taskDockStatus.style.color = "";
              }
              if (taskDockProgressText) taskDockProgressText.innerText = msg.summary || "Code prêt et vérifié.";
              if (taskDock) taskDock.style.borderColor = "rgba(6, 182, 212, 0.4)";
              setTimeout(() => {
                if (taskDock) taskDock.style.display = 'none';
                if (taskDock) taskDock.style.borderColor = '';
              }, 6000);
            }
          } else if (msg.type === 'browser_update') {
            if (msg.url) currentWebUrl = msg.url;
            if (msg.title) currentWebTitle = msg.title;
            browserDockTitle.innerText = currentWebTitle || currentWebUrl;
            modalBrowserTitle.innerText = currentWebTitle || "PAGE WEB OUVERTE";
            browserDock.style.display = 'flex';
          } else if (msg.type === 'email_sent') {
            if (emailDock) {
              if (emailDockSubject) emailDockSubject.innerText = msg.subject || "Rapport J.A.R.V.I.S.";
              if (emailDockRecipient) emailDockRecipient.innerText = msg.recipient || "pierrecassagnettes@gmail.com";
              if (emailDockStatus) {
                emailDockStatus.innerText = msg.status === 'sent' ? "TRANSMISSION RÉUSSIE" : "ARCHIVÉ DANS OUTBOX";
              }
              emailDock.style.display = 'flex';
              if (emailDockTimer) clearTimeout(emailDockTimer);
              emailDockTimer = setTimeout(() => {
                emailDock.style.display = 'none';
              }, 10000);
            }
          } else if (msg.type === 'paid_consent_request') {
            showPaidConsentModal(msg);
          } else if (msg.type === 'hide_paid_consent') {
            hidePaidConsentModal();
          } else if (msg.type === 'supervision_update') {
            if (msg.overview) {
              renderSupervisionOverview(msg.overview);
            }
          } else if (msg.type === 'transcript') {
            handleTranscript(msg.role, msg.text, msg.mode);
          } else if (msg.type === 'turn_complete') {
            // Signal de fin de génération reçu : attend la fin effective de lecture sonore
            // L'outil a terminé, on désactive le gating et le silence sender
            isToolExecuting = false;
            stopSilenceSender();
            turnCompletePending = true;
            if (scheduledAudioSources.length === 0) {
              checkSpeechEnded();
            }
          } else if (msg.type === 'interrupted') {
            isToolExecuting = false;
            stopSilenceSender();
            interruptPlayback();
            setJarvisState('listening', "À l'écoute...");
          } else if (msg.type === 'tool_start') {
            // Un outil vient de démarrer : activation immédiate du gating et du silence sender
            isToolExecuting = true;
            startSilenceSender();
          } else if (msg.type === 'tool_end') {
            // L'outil est terminé : Gemini va répondre avec de l'audio immédiatement
            // On désactive isToolExecuting SEULEMENT quand le premier chunk audio arrive (dans playPcmChunk)
            // pour éviter tout blanc entre la fin de l'outil et le début de la parole
            // isToolExecuting reste true jusqu'au premier PCM chunk reçu
          }
        } catch (err) {
          console.error("Erreur message JSON:", err);
        }
      } else if (event.data instanceof ArrayBuffer) {
        playPcmChunk(event.data);
      }
    };

    ws.onclose = (e) => {
      isConnecting = false;
      if (e.code === 1008) {
        disconnectJarvis("Terminal révoqué ou non autorisé");
        localStorage.removeItem('jarvis_device_token');
        authScreen.style.display = 'flex';
        authScreen.style.opacity = '1';
        mainScreen.style.display = 'none';
      } else {
        disconnectJarvis("Connexion terminée");
      }
    };

    ws.onerror = (err) => {
      isConnecting = false;
      disconnectJarvis("Erreur de connexion");
    };
  } catch (err) {
    isConnecting = false;
    disconnectJarvis("Erreur micro: " + (err.message || err));
  }
}

function disconnectJarvis(msg) {
  isConnecting = false;
  isConnected = false;
  stopLiveSpeechRecognition();
  interruptPlayback();
  isJarvisSpeaking = false;
  isToolExecuting = false;
  stopSilenceSender();
  turnCompletePending = false;
  if (btnInterrupt) btnInterrupt.style.display = 'none';
  if (micAnimFrame) {
    cancelAnimationFrame(micAnimFrame);
    micAnimFrame = null;
  }
  btn.classList.remove('active', 'state-listening', 'state-thinking', 'state-speaking', 'state-coding', 'state-browsing', 'state-emailing');
  btnLabel.innerText = "CONNECT";
  setJarvisState('offline', msg || "Session arrêtée");
  
  micText.innerText = "MICROPHONE INACTIF";
  micText.style.color = '#64748b';
  micDb.innerText = "- INF dB";
  micBars.forEach(b => { b.style.height = '4px'; b.style.background = '#0f172a'; });
  reactorHalo.style.transform = 'scale(1)';
  speakerAnalyser = null;
  speakerDataArray = null;
  animateAvatarSpeech(0);

  if (processor) {
    try { processor.disconnect(); } catch (e) {}
    processor = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  if (ws) {
    try {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      ws.close();
    } catch (e) {}
    ws = null;
  }
  if (audioCtx) {
    try { audioCtx.close(); } catch (e) {}
    audioCtx = null;
  }
}

btn.onclick = () => {
  if (isConnecting) return;
  if (!isConnected) {
    startJarvis();
  } else {
    // Si Jarvis est en train de parler, un clic interrompt la parole immédiatement pour poser une question !
    if (isJarvisSpeaking || scheduledAudioSources.length > 0) {
      interruptPlayback();
      setJarvisState('listening', "JARVIS à l'écoute, posez votre question...");
      return;
    }
    disconnectJarvis("Session déconnectée");
  }
};

// Actions du dock navigateur (Voir l'écran / Ouvrir le lien sur le smartphone)
btnViewBrowser.onclick = () => {
  browserScreenshotImg.src = "/static/latest_screenshot.jpg?t=" + Date.now();
  browserModal.style.display = 'flex';
};
btnOpenBrowser.onclick = () => {
  if (currentWebUrl) {
    window.open(currentWebUrl, '_blank');
  }
};
btnModalOpenExternal.onclick = () => {
  if (currentWebUrl) {
    window.open(currentWebUrl, '_blank');
  }
};
btnCloseBrowserModal.onclick = () => {
  browserModal.style.display = 'none';
};

// --- GUIDAGE ET ADAPTATION DE TÂCHE EN DIRECT ---
function sendLiveDirective(text) {
  if (!text || !text.trim()) return;
  const clean = text.trim();
  console.log("[Directive] Envoi de consigne en direct :", clean);

  // 1. Envoi prioritaire par WebSocket temps réel si connecté
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "live_directive", directive: clean }));
      return;
    } catch (e) {
      console.warn("Échec envoi WS direct, repli REST:", e);
    }
  }

  // 2. Repli fluide sur l'API REST
  fetch('/api/task/directive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directive: clean })
  })
  .then(r => r.json())
  .then(data => console.log("[Directive REST]:", data))
  .catch(err => console.error("Erreur transmission directive:", err));
}

if (btnSendDirective && taskDirectiveInput) {
  btnSendDirective.onclick = () => {
    const text = taskDirectiveInput.value.trim();
    if (text) {
      sendLiveDirective(text);
      taskDirectiveInput.value = '';
    }
  };
  taskDirectiveInput.onkeydown = (e) => {
    if (e.key === 'Enter') {
      const text = taskDirectiveInput.value.trim();
      if (text) {
        sendLiveDirective(text);
        taskDirectiveInput.value = '';
      }
    }
  };
}

// ========================================================
// MODULE DE SUPERVISION GLOBALE (MODÈLES, CLÉS API, ACTIONS & FENÊTRES)
// ========================================================

let supervisionPollTimer = null;

async function fetchSupervisionOverview() {
  const token = localStorage.getItem('jarvis_device_token') || getCookie('jarvis_device_token') || '';

  // 1. Demande prioritaire via WebSocket si connecté pour broadcast immédiat
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: 'get_supervision_overview' }));
    } catch (e) {
      console.warn("Échec requête supervision par WS:", e);
    }
  }

  // 2. Appel REST direct avec token pour garantir l'affichage même sans session vocale
  try {
    const url = '/api/supervision/overview' + (token ? '?token=' + encodeURIComponent(token) : '');
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      renderSupervisionOverview(data);
    }
  } catch (err) {
    console.warn("Erreur fetch supervision REST:", err);
  }
}

function openSupervisionModal() {
  if (!supervisionModal) return;
  supervisionModal.style.display = 'flex';
  fetchSupervisionOverview();
  
  if (!supervisionPollTimer) {
    supervisionPollTimer = setInterval(fetchSupervisionOverview, 2500);
  }
}

function closeSupervisionModal() {
  if (!supervisionModal) return;
  supervisionModal.style.display = 'none';
  if (supervisionPollTimer) {
    clearInterval(supervisionPollTimer);
    supervisionPollTimer = null;
  }
}

function setLiveModel(modelKey) {
  console.log("[Supervision] Changement de modèle vocal demandé :", modelKey);
  const token = localStorage.getItem('jarvis_device_token') || getCookie('jarvis_device_token') || '';

  // Via WebSocket si connecté
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: 'set_live_model', model: modelKey }));
    } catch (e) {
      console.warn("Erreur WS set_live_model:", e);
    }
  }
  // Et via REST
  const url = '/api/live-model' + (token ? '?token=' + encodeURIComponent(token) : '');
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelKey })
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      const newModelName = data.current_model || modelKey;
      window._currentLiveModelName = newModelName;
      if (engineModelText && !isToolExecuting) {
        engineModelText.innerText = newModelName.toUpperCase();
      }
      fetchSupervisionOverview();
    }
  })
  .catch(e => console.warn("Erreur bascule modèle REST:", e));
}

function renderSupervisionOverview(data) {
  if (!data) return;

  // 1. MODÈLE VOCAL ACTIF & CLÉ
  if (data.voice) {
    const vModel = data.voice.display_label || data.voice.model || "Gemini 3.8 Live";
    window._currentLiveModelName = vModel;
    if (supVoiceModel) supVoiceModel.innerText = vModel.toUpperCase();
    if (supVoiceDetail) supVoiceDetail.innerText = `Voix : ${data.voice.voice_name || 'Aoede'} (Féminine, Naturelle & Distinguée)`;

    if (supVoiceStatusTag) {
      const st = (data.voice.status || data.voice.state || 'CONNECTÉ').toUpperCase();
      supVoiceStatusTag.innerText = st;
      if (st.includes('PAROLE') || st.includes('SPEAKING')) {
        supVoiceStatusTag.style.background = 'rgba(0, 240, 255, 0.2)';
        supVoiceStatusTag.style.color = '#00f0ff';
      } else if (st.includes('RÉFLEXION') || st.includes('THINKING')) {
        supVoiceStatusTag.style.background = 'rgba(245, 158, 11, 0.2)';
        supVoiceStatusTag.style.color = '#fbbf24';
      } else {
        supVoiceStatusTag.style.background = 'rgba(56, 189, 248, 0.15)';
        supVoiceStatusTag.style.color = '#38bdf8';
      }
    }

    const isPaidVoice = data.voice.is_paid || (data.voice.api_type === 'paid');
    if (supVoiceKeyPill) {
      if (isPaidVoice) {
        supVoiceKeyPill.className = 'badge-key-pill badge-key-paid';
        supVoiceKeyPill.innerText = (data.voice.api_label && data.voice.api_label.toLowerCase().includes('repli')) 
          ? 'CLÉ PAYANTE (REPLI)' 
          : 'CLÉ PAYANTE';
      } else {
        supVoiceKeyPill.className = 'badge-key-pill badge-key-free';
        supVoiceKeyPill.innerText = 'CLÉ GRATUITE';
      }
    }

    if (supVoiceCost) supVoiceCost.innerText = isPaidVoice ? "~0.005 $" : "0.00 $ (Plan Gratuit)";
    if (supVoiceKeyMasked) {
      supVoiceKeyMasked.innerText = data.voice.api_key_masked ? `•••• ${data.voice.api_key_masked}` : 'NON CONFIGURÉE';
    }

    // Mise à jour de l'indicateur HUD principal
    if (engineModelText && !isToolExecuting) {
      engineModelText.innerText = vModel.toUpperCase();
    }

    // Boutons de bascule rapide de modèle
    const isThinking = (data.voice.model || '').toLowerCase().includes('thinking');
    if (btnSwitchLiveStd) btnSwitchLiveStd.classList.toggle('active', !isThinking);
    if (btnSwitchLiveThinking) btnSwitchLiveThinking.classList.toggle('active', isThinking);
  }

  // 2. ACTIONS EN COURS
  const activeActions = data.active_actions || (data.actions && data.actions.active_actions) || [];
  const actionCount = (typeof data.running_count === 'number') ? data.running_count : activeActions.length;

  if (supActionsCountBadge) {
    supActionsCountBadge.innerText = `${actionCount} ACTIVE${actionCount > 1 ? 'S' : ''}`;
  }

  // Badges d'alerte sur le HUD principal
  if (supervisionActionBadge) {
    if (actionCount > 0) {
      supervisionActionBadge.style.display = 'inline-flex';
      supervisionActionBadge.innerText = actionCount;
    } else {
      supervisionActionBadge.style.display = 'none';
    }
  }
  if (engineActionsBadge) {
    if (actionCount > 0) {
      engineActionsBadge.style.display = 'inline-flex';
      if (engineActionsCount) engineActionsCount.innerText = `${actionCount} EN COURS`;
    } else {
      engineActionsBadge.style.display = 'none';
    }
  }

  if (supActiveActionsContainer) {
    if (actionCount === 0) {
      supActiveActionsContainer.innerHTML = `
        <div class="sup-empty-state">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <span>Aucune tâche lourde en cours d'exécution. JARVIS est en veille active.</span>
        </div>
      `;
    } else {
      supActiveActionsContainer.innerHTML = activeActions.map(act => {
        const isPaid = act.is_paid || (act.key_type === 'paid') || (act.api_type === 'paid');
        const progress = Math.max(5, Math.min(100, Math.round(act.progress || 0)));
        return `
          <div class="sup-action-card">
            <div class="sup-action-header">
              <div class="sup-action-title">
                <span class="sup-action-dot"></span>
                <strong>${escapeHtml(act.title || act.type || 'Action')}</strong>
              </div>
              <span class="badge-key-pill ${isPaid ? 'badge-key-paid' : 'badge-key-free'}">
                ${isPaid ? 'CLÉ PAYANTE' : 'CLÉ GRATUITE'}
              </span>
            </div>
            <div class="sup-action-meta">
              <span><strong>Moteur :</strong> ${escapeHtml(act.engine || 'Système')}</span>
              <span><strong>Modèle :</strong> ${escapeHtml(act.model || 'Standard')}</span>
              ${act.cost_estimate ? `<span><strong>Coût :</strong> ${escapeHtml(act.cost_estimate)}</span>` : ''}
            </div>
            ${act.instruction ? `<div class="sup-action-instruction">${escapeHtml(act.instruction)}</div>` : ''}
            <div class="sup-action-progress-container">
              <div class="sup-action-progress-bar" style="width: ${progress}%"></div>
            </div>
            <div class="sup-action-footer">
              <span>${escapeHtml(act.status || 'En cours')}</span>
              <span>${progress}%</span>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // 3. OUTILS DU SYSTÈME & REGISTRE DES APIS
  if (supToolsTable && data.tools) {
    const tools = data.tools;
    supToolsTable.innerHTML = `
      <div class="sup-table-header">
        <div>OUTIL</div>
        <div>MODÈLE UTILISÉ</div>
        <div>CLÉ / TARIFICATION</div>
        <div style="text-align: right;">STATUT</div>
      </div>
      ${tools.map(tool => {
        const isPaid = (tool.api_type === 'paid') || tool.is_paid;
        const isHybrid = (tool.api_type === 'hybrid');
        const isRunning = tool.active || tool.is_running || false;
        let badgeClass = 'badge-key-free';
        let badgeText = 'CLÉ GRATUITE';
        if (isPaid) {
          badgeClass = 'badge-key-paid';
          badgeText = 'CLÉ PAYANTE';
        } else if (isHybrid) {
          badgeClass = 'badge-key-free';
          badgeText = 'GRATUITE / PAYANTE';
        } else if (tool.api_type === 'local') {
          badgeClass = 'badge-key-free';
          badgeText = 'LOCAL (0.00$)';
        }

        return `
          <div class="sup-tool-row ${isRunning ? 'tool-running' : ''}">
            <div class="sup-tool-col-name">
              <span class="sup-tool-icon">${tool.icon || '⚙️'}</span>
              <div>
                <div class="sup-tool-name">${escapeHtml(tool.name)}</div>
                <div class="sup-tool-desc">${escapeHtml(tool.description)}</div>
              </div>
            </div>
            <div class="sup-tool-col-model">
              <span class="sup-model-tag">${escapeHtml(tool.model)}</span>
            </div>
            <div class="sup-tool-col-key">
              <span class="badge-key-pill ${badgeClass}">
                ${badgeText}
              </span>
              <span class="sup-tool-cost">${escapeHtml(tool.cost_est || tool.cost_note || '')}</span>
            </div>
            <div class="sup-tool-col-status">
              <span class="sup-status-pill ${isRunning ? 'status-active' : 'status-idle'}">
                ${isRunning ? '● EN COURS' : 'AU REPOS'}
              </span>
            </div>
          </div>
        `;
      }).join('')}
    `;
  }

  // 4. FENÊTRES OUVERTES (SYSTÈME & NAVIGATEUR)
  const rawWindows = data.open_windows || (data.windows && data.windows.windows) || [];
  if (supWindowsList) {
    const totalCount = (data.windows && data.windows.total_count) ? data.windows.total_count : rawWindows.length;
    if (supWindowsCountBadge) {
      supWindowsCountBadge.innerText = `${totalCount} FENÊTRE${totalCount > 1 ? 'S' : ''}`;
    }

    if (rawWindows.length === 0) {
      supWindowsList.innerHTML = `
        <div class="sup-empty-state">
          <span>Aucune fenêtre active détectée.</span>
        </div>
      `;
    } else {
      supWindowsList.innerHTML = rawWindows.map(win => {
        const isJarvis = win.is_jarvis || (win.opened_by && win.opened_by.toLowerCase().includes('jarvis'));
        const hasUrl = !!win.url;
        let icon = '🪟';
        const titleLower = (win.title || '').toLowerCase();
        const procLower = (win.process || '').toLowerCase();
        if (procLower.includes('edge') || procLower.includes('chrome') || procLower.includes('firefox') || win.type === 'browser') {
          icon = '🌐';
        } else if (procLower.includes('code') || titleLower.includes('visual studio') || titleLower.includes('.py')) {
          icon = '💻';
        } else if (procLower.includes('terminal') || procLower.includes('cmd') || procLower.includes('powershell')) {
          icon = '⌨️';
        } else if (procLower.includes('explorer')) {
          icon = '📁';
        }

        return `
          <div class="sup-window-card ${isJarvis ? 'window-jarvis' : ''}">
            <span class="sup-window-icon">${icon}</span>
            <div class="sup-window-info">
              <div class="sup-window-title" title="${escapeHtml(win.title)}">${escapeHtml(win.title)}</div>
              <div class="sup-window-sub">
                ${win.process ? `<span class="sup-proc-tag">${escapeHtml(win.process)}</span>` : ''}
                ${isJarvis ? '<span class="sup-jarvis-badge">OUVERTE PAR JARVIS</span>' : '<span class="sup-sys-badge">SYSTÈME WINDOWS</span>'}
                ${hasUrl ? `<a href="${escapeHtml(win.url)}" target="_blank" class="sup-win-link">Ouvrir le lien ↗</a>` : ''}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // 5. SYNTHÈSE DES CLÉS API
  if (data.api_keys) {
    const freeMasked = (data.api_keys.free_key && data.api_keys.free_key.masked) || data.api_keys.free_key_masked;
    const paidMasked = (data.api_keys.paid_key && data.api_keys.paid_key.masked) || data.api_keys.paid_key_masked;
    const isFreeExhausted = data.api_keys.free_key && data.api_keys.free_key.exhausted;

    if (supSummaryFreeKey) {
      supSummaryFreeKey.innerText = freeMasked ? `•••• ${freeMasked}` : 'NON DÉFINIE';
    }
    if (supSummaryPaidKey) {
      supSummaryPaidKey.innerText = paidMasked ? `•••• ${paidMasked}` : 'NON DÉFINIE';
    }
    const supSummaryFreeBadge = document.getElementById('supSummaryFreeBadge');
    const supSummaryFreeStatus = document.getElementById('supSummaryFreeStatus');
    const supSummaryPaidStatus = document.getElementById('supSummaryPaidStatus');

    if (supSummaryFreeBadge) {
      if (isFreeExhausted) {
        supSummaryFreeBadge.innerText = 'QUOTA ÉPUISÉ';
        supSummaryFreeBadge.className = 'badge-key-pill badge-key-thinking';
      } else {
        supSummaryFreeBadge.innerText = freeMasked ? 'PAR DÉFAUT' : 'NON CONFIGURÉE';
        supSummaryFreeBadge.className = 'badge-key-pill ' + (freeMasked ? 'badge-key-free' : 'badge-key-thinking');
      }
    }
    if (supSummaryFreeStatus) {
      if (isFreeExhausted) {
        supSummaryFreeStatus.innerText = 'Quota dépassé - Repli sur clé payante';
        supSummaryFreeStatus.style.color = '#f59e0b';
      } else {
        supSummaryFreeStatus.innerText = 'Active par défaut (0.00 $ - Inclus)';
        supSummaryFreeStatus.style.color = '#38bdf8';
      }
    }

    if (supSummaryPaidBadge) {
      supSummaryPaidBadge.innerText = paidMasked ? (isFreeExhausted ? 'ACTIVE (REPLI EN COURS)' : 'ACTIVE') : 'NON CONFIGURÉE';
      supSummaryPaidBadge.className = 'badge-key-pill ' + (paidMasked ? 'badge-key-paid' : 'badge-key-free');
    }
    if (supSummaryPaidStatus) {
      if (isFreeExhausted) {
        supSummaryPaidStatus.innerText = 'Voix Live, Thinking, Flash & Antigravity';
        supSummaryPaidStatus.style.color = '#a855f7';
      } else {
        supSummaryPaidStatus.innerText = 'Thinking, Flash, Antigravity & Repli';
        supSummaryPaidStatus.style.color = '#a855f7';
      }
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialisation des écouteurs d'événements pour le modal de supervision
if (btnOpenOverview) {
  btnOpenOverview.onclick = openSupervisionModal;
}
if (engineChip) {
  engineChip.onclick = openSupervisionModal;
}
if (btnCloseSupervision) {
  btnCloseSupervision.onclick = closeSupervisionModal;
}
if (btnCloseSupervisionFooter) {
  btnCloseSupervisionFooter.onclick = closeSupervisionModal;
}
if (btnRefreshSupervision) {
  btnRefreshSupervision.onclick = () => {
    fetchSupervisionOverview();
  };
}

if (btnSwitchLiveStd) {
  btnSwitchLiveStd.onclick = () => {
    setLiveModel('gemini-3.8-live');
  };
}
if (btnSwitchLiveThinking) {
  btnSwitchLiveThinking.onclick = () => {
    setLiveModel('gemini-3.8-live-extended-thinking');
  };
}

// Fermeture par touche Echap ou clic sur l'overlay
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && supervisionModal && supervisionModal.style.display !== 'none') {
    closeSupervisionModal();
  }
});
if (supervisionModal) {
  supervisionModal.addEventListener('click', (e) => {
    if (e.target === supervisionModal) {
      closeSupervisionModal();
    }
  });
}

// Initialisation dès le chargement de la page
fetchSupervisionOverview();

// Nettoyage strict lors de la fermeture, rechargement ou masquage de la page pour éviter les sessions zombies
window.addEventListener('beforeunload', () => {
  disconnectJarvis("Page fermée");
});
window.addEventListener('pagehide', () => {
  disconnectJarvis("Page masquée");
});
