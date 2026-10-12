import sys
import time
import serial

PORT = "COM5"
BAUD = 115200

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"[Monitor] Connecté à {PORT} ({BAUD} bauds). Écoute des logs (10s)...")
    start = time.time()
    while time.time() - start < 10:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='replace').rstrip()
            if line:
                print(line)
        time.sleep(0.05)
    ser.close()
    print("[Monitor] Fin d'écoute.")
except Exception as e:
    print(f"[Monitor] Erreur d'ouverture du port {PORT} : {e}")
