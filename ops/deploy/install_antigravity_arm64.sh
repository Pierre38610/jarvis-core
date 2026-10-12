#!/bin/bash
# Installation globale d'Antigravity CLI pour architecture ARM64 (aarch64) sur le VPS Oracle

set -e

echo "[1/4] Mise à jour des paquets et installation des dépendances système..."
sudo apt-get update -y
sudo apt-get install -y curl nodejs npm python3-pip

echo "[2/4] Installation globale d'Antigravity CLI..."
# Si c'est un package npm
sudo npm install -g @google/antigravity-cli || echo "npm install a échoué, tentative via pip..."
# Si c'est un package pip
sudo pip3 install --upgrade antigravity-cli || echo "pip install a échoué, vérifiez le nom du paquet officiel."

echo "[3/4] Mise en place de la structure de stockage des identifiants..."
mkdir -p /home/opc/.config/antigravity
sudo chown -R opc:opc /home/opc/.config/antigravity
sudo chmod 700 /home/opc/.config/antigravity

echo "[4/4] Vérification de l'installation..."
if command -v antigravity-cli >/dev/null 2>&1; then
    echo "Antigravity CLI est installé :"
    antigravity-cli --version
else
    echo "Attention : antigravity-cli n'est pas dans le PATH."
fi

echo "=========================================================="
echo "Installation terminée. Pour vérifier la session, exécutez :"
echo "antigravity-cli auth status"
echo "=========================================================="
