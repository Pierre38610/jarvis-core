# Jeu classique du Snake développé avec Tkinter : gestion des déplacements, de la détection de collision et du score.
# Commentaire clair : Implémentation complète d'un jeu Snake autonome avec boucle d'événements Tkinter, contrôles clavier (flèches et ZQSD/WASD), génération de nourriture et détection des collisions.
import tkinter as tk
import random

# Configuration du jeu
LARGEUR_CANVAS = 400
HAUTEUR_CANVAS = 400
TAILLE_CASE = 20
VITESSE = 100  # Millisecondes entre chaque mouvement (plus petit = plus rapide)

class JeuSnake:
    def __init__(self, fenetre):
        self.fenetre = fenetre
        self.fenetre.title("Jeu de Snake")
        self.fenetre.resizable(False, False)

        # Score et état du jeu
        self.score = 0
        self.en_cours = True

        # Widgets
        self.label_score = tk.Label(fenetre, text=f"Score: {self.score}", font=("Arial", 14))
        self.label_score.pack()

        self.canvas = tk.Canvas(fenetre, bg="black", width=LARGEUR_CANVAS, height=HAUTEUR_CANVAS)
        self.canvas.pack()

        # Binding des touches clavier
        self.fenetre.bind("<Left>", lambda e: self.changer_direction("gauche"))
        self.fenetre.bind("<Right>", lambda e: self.changer_direction("droite"))
        self.fenetre.bind("<Up>", lambda e: self.changer_direction("haut"))
        self.fenetre.bind("<Down>", lambda e: self.changer_direction("bas"))
        
        # Support additionnel pour ZQSD / WASD
        self.fenetre.bind("<q>", lambda e: self.changer_direction("gauche"))
        self.fenetre.bind("<d>", lambda e: self.changer_direction("droite"))
        self.fenetre.bind("<z>", lambda e: self.changer_direction("haut"))
        self.fenetre.bind("<s>", lambda e: self.changer_direction("bas"))
        self.fenetre.bind("<a>", lambda e: self.changer_direction("gauche")) # Pour claviers QWERTY
        self.fenetre.bind("<w>", lambda e: self.changer_direction("haut"))

        self.fenetre.bind("<space>", lambda e: self.reinitialiser_jeu())

        # Démarrage
        self.reinitialiser_jeu()

    # Commentaire clair : Réinitialise l'état global de la partie (score à zéro, repositionnement du serpent au centre et génération d'une nouvelle pomme).
    def reinitialiser_jeu(self):
        self.score = 0
        self.label_score.config(text=f"Score: {self.score}")
        self.en_cours = True
        
        # Position initiale du serpent (3 segments au milieu de l'écran)
        self.serpent = [
            (LARGEUR_CANVAS // 2, HAUTEUR_CANVAS // 2),
            (LARGEUR_CANVAS // 2 - TAILLE_CASE, HAUTEUR_CANVAS // 2),
            (LARGEUR_CANVAS // 2 - (2 * TAILLE_CASE), HAUTEUR_CANVAS // 2)
        ]
        self.direction = "droite"
        
        # Placement de la première nourriture
        self.placer_nourriture()
        
        # Lancement de la boucle de jeu
        self.actualiser()

    def placer_nourriture(self):
        # Générer des coordonnées aléatoires qui s'alignent avec la grille
        while True:
            x = random.randint(0, (LARGEUR_CANVAS // TAILLE_CASE) - 1) * TAILLE_CASE
            y = random.randint(0, (HAUTEUR_CANVAS // TAILLE_CASE) - 1) * TAILLE_CASE
            self.nourriture = (x, y)
            # S'assurer que la nourriture n'apparaît pas sur le serpent
            if self.nourriture not in self.serpent:
                break

    # Commentaire clair : Met à jour la direction actuelle du serpent tout en empêchant les demi-tours immédiats à 180 degrés
    def changer_direction(self, nouvelle_direction):
        # Empêcher le serpent de faire un demi-tour direct sur lui-même
        opposés = {
            "gauche": "droite",
            "droite": "gauche",
            "haut": "bas",
            "bas": "haut"
        }
        if nouvelle_direction != opposés.get(self.direction):
            self.direction = nouvelle_direction

    # Commentaire clair : Détecte si la tête du serpent heurte les limites de la grille ou son propre corps
    def verifier_collisions(self, tete):
        x, y = tete
        # Collision avec les bords
        if x < 0 or x >= LARGEUR_CANVAS or y < 0 or y >= HAUTEUR_CANVAS:
            return True
        # Collision avec son propre corps
        if tete in self.serpent[1:]:
            return True
        return False

    def actualiser(self):
        if not self.en_cours:
            return

        # Calculer la nouvelle position de la tête
        tete_x, tete_y = self.serpent[0]
        if self.direction == "gauche":
            tete_x -= TAILLE_CASE
        elif self.direction == "droite":
            tete_x += TAILLE_CASE
        elif self.direction == "haut":
            tete_y -= TAILLE_CASE
        elif self.direction == "bas":
            tete_y += TAILLE_CASE

        nouvelle_tete = (tete_x, tete_y)

        # Vérifier si on a perdu
        if self.verifier_collisions(nouvelle_tete):
            self.en_cours = False
            self.afficher_game_over()
            return

        # Ajouter la nouvelle tête au serpent
        self.serpent.insert(0, nouvelle_tete)

        # Vérifier si on mange de la nourriture
        if nouvelle_tete == self.nourriture:
            self.score += 10
            self.label_score.config(text=f"Score: {self.score}")
            self.placer_nourriture()
        else:
            # Retirer le dernier segment pour simuler le mouvement s'il ne grandit pas
            self.serpent.pop()

        # Redessiner le canvas
        self.dessiner()

        # Planifier la prochaine mise à jour
        self.fenetre.after(VITESSE, self.actualiser)

    def dessiner(self):
        self.canvas.delete("all")

        # Dessiner la nourriture en rouge
        nx, ny = self.nourriture
        self.canvas.create_oval(nx, ny, nx + TAILLE_CASE, ny + TAILLE_CASE, fill="red", outline="darkred")

        # Dessiner le serpent en vert
        for i, (sx, sy) in enumerate(self.serpent):
            couleur = "darkgreen" if i == 0 else "green"  # Tête légèrement plus foncée
            self.canvas.create_rectangle(sx, sy, sx + TAILLE_CASE, sy + TAILLE_CASE, fill=couleur, outline="black")

    def afficher_game_over(self):
        self.canvas.delete("all")
        self.canvas.create_text(
            LARGEUR_CANVAS // 2, HAUTEUR_CANVAS // 2 - 20,
            text="GAME OVER", fill="red", font=("Arial", 24, "bold")
        )
        self.canvas.create_text(
            LARGEUR_CANVAS // 2, HAUTEUR_CANVAS // 2 + 20,
            text="Appuyez sur ESPACE pour recommencer", fill="white", font=("Arial", 12)
        )

# Démarrage de l'application
if __name__ == "__main__":
    racine = tk.Tk()
    jeu = JeuSnake(racine)
    racine.mainloop()
