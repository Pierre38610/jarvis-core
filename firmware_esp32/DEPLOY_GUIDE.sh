# ════════════════════════════════════════════════════════════════════════════════
# FIRMWARE J.A.R.V.I.S. ESP32-S3 — Guide de déploiement complet
# Waveshare ESP32-S3-AUDIO-Board | Wake word : "Jarvis" (wn9_jarvis_tts)
# ════════════════════════════════════════════════════════════════════════════════

# ─── ÉTAPE 1 : Cloner xiaozhi-esp32 ────────────────────────────────────────────
git clone https://github.com/78/xiaozhi-esp32.git jarvis-esp32
cd jarvis-esp32
git submodule update --init --recursive

idf.py set-target esp32s3

# ─── ÉTAPE 2 : menuconfig ───────────────────────────────────────────────────────
# Board Selection → Waveshare ESP32-S3-AUDIO-Board
# Wake Word Engine → WakeNet → wn9_jarvis_tts
# WebSocket URL → wss://jarvis.signalcraftapps.com/ws/device
idf.py menuconfig

# ─── ÉTAPE 3 : Générer le token JWT device ─────────────────────────────────────
# Depuis PowerShell :
#   Invoke-RestMethod -Method POST `
#     -Uri "https://jarvis.signalcraftapps.com/api/device/generate-token" `
#     -ContentType "application/json" `
#     -Body '{"device_name":"Waveshare ESP32-S3 Speaker","mac_address":"a0:f2:62:e3:63:6c","admin_password":"<MOT_DE_PASSE>"}'
#
# Récupérer : token, device_id

# ─── ÉTAPE 4 : sdkconfig.defaults ──────────────────────────────────────────────
# Ajouter à la racine du projet (jarvis-esp32/sdkconfig.defaults) :
CONFIG_BOARD_WAVESHARE_ESP32_S3_AUDIO=y
CONFIG_SR_WN_WN9_JARVIS_TTS=y
CONFIG_WEBSOCKET_URI="wss://jarvis.signalcraftapps.com/ws/device"
CONFIG_INPUT_SAMPLE_RATE=16000
CONFIG_OUTPUT_SAMPLE_RATE=24000

# ─── ÉTAPE 5 : Patch WebSocket auth header ─────────────────────────────────────
# Fichier : main/network/websocket_client.cc (ou similaire)
# Dans esp_websocket_client_config_t, ajouter :
#   .headers = "Authorization: Bearer " JARVIS_DEVICE_TOKEN "\r\n",
#   .user_agent = "ESP32-S3-Jarvis/1.0",
# Lire le token depuis NVS :
#   nvs_get_str(nvs_handle, "device_token", token_buf, &token_len);

# ─── ÉTAPE 6 : Build + Flash ────────────────────────────────────────────────────
idf.py build
idf.py -p COM5 flash

# ─── ÉTAPE 7 : Flash NVS (token + wifi) ────────────────────────────────────────
# Créer nvs_values.csv :
#   key,type,encoding,value
#   device_token,data,string,<JWT_TOKEN>
#   device_id,data,string,<DEVICE_ID>
#   server_url,data,string,wss://jarvis.signalcraftapps.com/ws/device
#   wifi_ssid,data,string,<SSID>
#   wifi_password,data,string,<MOT_DE_PASSE_WIFI>
#
# Générer la partition NVS binaire :
python $IDF_PATH/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py \
  generate nvs_values.csv nvs_jarvis.bin 0x6000
#
# Flasher la partition NVS à l'adresse 0x9000 :
python -m esptool --port COM5 --baud 460800 write_flash 0x9000 nvs_jarvis.bin

# ─── ÉTAPE 8 : Monitor ─────────────────────────────────────────────────────────
idf.py -p COM5 monitor
# Sortie attendue :
# [ws] Connexion WSS → wss://jarvis.signalcraftapps.com/ws/device
# [ws] {"type":"welcome","server":"J.A.R.V.I.S.","version":"5.x.x"}
# [sr] WakeNet wn9_jarvis_tts initialisé
# [sr] En attente du mot de réveil "Jarvis"...

# ─── ÉTAPE 9 : Valider ─────────────────────────────────────────────────────────
# Dire "Jarvis" → LED cyan, question → réponse audio
# GET https://jarvis.signalcraftapps.com/api/device/sessions?token=<admin_token>
