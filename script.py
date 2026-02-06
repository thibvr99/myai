from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import json
import os
import time
import pywhatkit
import pyautogui
import subprocess
import pygetwindow as gw
from urllib.parse import quote
import threading

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
OFFSET_VERTICAL_HEADER = 260
OFFSET_HORIZONTAL = 100

NOM_DU_PC = "FIXE" 
PORT_ECOUTE = 5000 
IP_CERVEAU = "192.168.0.120" # <--- VÉRIFIEZ L'IP DU CERVEAU
PORT_LM = "1234"

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE = "Profile 2"
# ==========================================

app = Flask(__name__)
CORS(app)
client = OpenAI(base_url=f"http://{IP_CERVEAU}:{PORT_LM}/v1", api_key="lm-studio")

def focus_window_containing(title_part):
    """Active la première fenêtre qui contient 'title_part' dans son titre."""
    try:
        windows = gw.getAllWindows()
        for win in windows:
            if title_part.lower() in win.title.lower():
                if win.isMinimized: win.restore()
                win.activate()
                time.sleep(0.2) # Petit délai pour être sûr
                return True
        return False
    except Exception as e:
        print(f"Erreur focus : {e}")
        return False

def executer_commande(user_input, platform_context):
    """
    platform_context : 'spotify' ou 'youtube' (envoyé par le bouton de l'interface)
    """
    system_prompt = """
    Tu es un assistant système. Réponds UNIQUEMENT en JSON.
    
    RÈGLE DE DÉFAUT (IMPORTANTE) :
    Si l'entrée de l'utilisateur ne contient pas de commande explicite (comme "pause", "volume", "monte"),
    tu DOIS considérer que c'est un TITRE DE MUSIQUE et générer une action "play".
    Même si c'est une phrase comme "I believe" ou "C'est la vie", c'est un titre.

    RÈGLE CRUCIALE POUR LA RECHERCHE :
    Ne jamais résumer. Garde tous les mots.

    TYPES POSSIBLES :
    - "play" : Lancer une recherche (Action par DÉFAUT).
    - "control" : Contrôler la lecture (Pause, Play, Suivant, Précédent).
    - "volume" : Actions : "increase", "decrease", "mute".

    Exemples :
    User: "Mets pause" -> {"type": "control", "action": "pause"}
    User: "Monte le son" -> {"type": "volume", "action": "increase"}
    
    User: "Joue Asake" -> {"type": "play", "query": "Asake"}
    User: "I believe" -> {"type": "play", "query": "I believe"}
    User: "Rat des villes" -> {"type": "play", "query": "Rat des villes"}
    User: "Booba" -> {"type": "play", "query": "Booba"}
    """

    print(f"🧠 Analyse : '{user_input}' pour la plateforme '{platform_context}'...")
    
    try:
        completion = client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.0,
        )

        response_text = completion.choices[0].message.content
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        
        if start != -1 and end != 0:
            data = json.loads(response_text[start:end])
            
            # Si l'IA ne précise pas la plateforme (cas play/control), on utilise celle sélectionnée sur l'UI
            target_platform = data.get('platform', platform_context).lower()

            # --- 1. GESTION DU VOLUME (Commun) ---
            if data['type'] == 'volume':
                action = data['action']
                if action == 'increase': 
                    for _ in range(5): pyautogui.press('volumeup')
                elif action == 'decrease': 
                    for _ in range(5): pyautogui.press('volumedown')
                elif action == 'mute': pyautogui.press('volumemute')

            # --- 2. CONTRÔLE (Pause, Suivant...) ---
            elif data['type'] == 'control':
                action = data['action']
                print(f"⏯️ Contrôle : {action} sur {target_platform}")

                if target_platform == 'spotify':
                    # Focus Spotify pour utiliser ses raccourcis
                    focus_window_containing("Spotify")
                    
                    if action in ['pause', 'play']: pyautogui.press('space') # Espace = Play/Pause
                    elif action == 'next': pyautogui.hotkey('ctrl', 'right')
                    elif action == 'prev': pyautogui.hotkey('ctrl', 'left')
                
                elif target_platform == 'youtube':
                    # Focus Navigateur (Chrome, Firefox, Edge...)
                    # On tente les noms communs
                    found = focus_window_containing("YouTube") or focus_window_containing("Chrome") or focus_window_containing("Edge") or focus_window_containing("Firefox")
                    
                    if found:
                        if action in ['pause', 'play']: pyautogui.press('k') # K = Play/Pause universel YouTube
                        elif action == 'next': pyautogui.hotkey('shift', 'n') # Suivant
                        elif action == 'previous': pyautogui.press('j') # Recul de 10s (Précédent playlist est complexe)

            # --- 3. LANCEMENT RECHERCHE (Play) ---
            elif data['type'] == 'play':
                query = data['query'].replace("lance ", "").replace("joue ", "").strip()
                print(f"✅ Lancement sur {target_platform} : {query}")

                if target_platform == 'youtube':
                    print(f"🚀 Action YouTube sur profil : {CHROME_PROFILE}")
                    url_youtube = f"https://www.youtube.com/results?search_query={quote(query)}"
                    url_youtube_nohttps = f"www.youtube.com/results?search_query={quote(query)}"

                    # --- LOGIQUE DE RÉUTILISATION D'ONGLET ---
                    existing_window = None
                    # On cherche parmi toutes les fenêtres ouvertes
                    for win in gw.getAllWindows():
                        # On cherche une fenêtre qui contient "YouTube" ET "Google Chrome" dans le titre
                        if "YouTube" in win.title and "Google Chrome" in win.title:
                            existing_window = win
                            break
                    
                    if existing_window:
                        print("🔄 Fenêtre YouTube détectée : Réutilisation...")
                        try:
                            if existing_window.isMinimized: existing_window.restore()
                            existing_window.activate()
                            time.sleep(0.5) # Pause vitale pour laisser Windows faire la mise au point
                            
                            # 1. Focus barre d'adresse (Ctrl+L est universel sur les navigateurs)
                            pyautogui.hotkey('ctrl', 'l') 
                            time.sleep(0.1)
                            
                            # 2. On écrit la nouvelle URL et on valide
                            pyautogui.write(url_youtube_nohttps)
                            pyautogui.press('enter')
                        except Exception as e:
                            print(f"⚠️ Erreur lors de la réutilisation : {e}")
                            # En cas d'erreur, on force l'ouverture classique
                            subprocess.Popen([CHROME_PATH, f"--profile-directory={CHROME_PROFILE}", url_youtube])
                            
                    else:
                        print("🆕 Aucune fenêtre trouvée : Lancement propre...")
                        # Commande pour forcer le profil spécifique (Votre méthode précédente)
                        subprocess.Popen([
                            CHROME_PATH, 
                            f"--profile-directory={CHROME_PROFILE}", 
                            url_youtube
                        ])

                    # --- SUITE (Auto-clic optionnel) ---
                    # On attend que la page charge (que ce soit refresh ou nouvelle fenêtre)
                    time.sleep(2) 
                    
                    # On s'assure qu'on est bien sur la fenêtre pour cliquer
                    focus_window_containing("YouTube")
                    
                    # Logique de clic pour lancer la première vidéo
                    win = gw.getActiveWindow()
                    if win:
                        # Clic au milieu un peu vers le haut (à ajuster selon votre écran)
                        # Le -100 en X sert à éviter les filtres latéraux
                        pyautogui.click(win.left + (win.width / 2) - 100, win.top + 350)
                
                elif target_platform == 'spotify':
                    # Votre logique existante Spotify
                    recherche_encodee = quote(query.replace("-", " "))
                    os.startfile(f"spotify:search:{recherche_encodee}")
                    time.sleep(2.5)
                    focus_window_containing("Spotify")
                    
                    # Logique de clic (simplifiée ici pour l'exemple, reprenez votre code complet si besoin)
                    win = gw.getActiveWindow()
                    pyautogui.press('tab')
                    if win:
                        target_x = win.left + 830  
                        target_y = win.top + 390
                        pyautogui.moveTo(target_x, target_y)
                        pyautogui.click()

    except Exception as e:
        print(f"❌ Erreur : {e}")

@app.route('/commande', methods=['POST'])
def recevoir_commande():
    data = request.json
    ordre = data.get('ordre')
    # NOUVEAU : On récupère la plateforme choisie sur l'UI
    platform = data.get('platform', 'spotify') 
    
    if not ordre: return jsonify({"status": "error"}), 400
    
    threading.Thread(target=executer_commande, args=(ordre, platform)).start()
    return jsonify({"status": "success"})

@app.route('/')
def home():
    return render_template('telecommande.html')

if __name__ == '__main__':
    print(f"📡 {NOM_DU_PC} écoute sur le port {PORT_ECOUTE}...")
    app.run(host='0.0.0.0', port=PORT_ECOUTE)