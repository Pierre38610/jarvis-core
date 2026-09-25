# Ce script est un exemple d'implémentation d'une opération mathématique basique (addition) avec affichage console.
# Commentaire clair : Ce module fournit une fonction d'addition simple 'addition(a, b)' et un point d'entrée exécutable pour tester le calcul arithmétique.
# Commentaire clair : Fonctionnement pas à pas : les variables sont définies dans main(), transmises à addition(), et le total est affiché dans la console.
"""Script simple effectuant une addition."""

# Commentaire clair : Fonction pure qui calcule la somme de deux nombres réels (flottants ou entiers) et retourne le résultat sans effet de bord.
# Commentaire clair : Effectue l'opération a + b et garantit un retour numérique cohérent.
def addition(a: float, b: float) -> float:
    # Calcule et renvoie la somme arithmétique de deux nombres
    """Retourne la somme de a et b."""
    # Commentaire clair : Renvoie l'addition directe des arguments 'a' et 'b'
    return a + b



def main():
    # Commentaire clair : Initialisation des deux nombres opérandes pour exécuter l'addition
    # Définition des valeurs d'entrée pour la démonstration
    nombre1 = 5
    nombre2 = 7
    # Commentaire clair : Calcul de la somme des deux entiers et affichage du résultat dans le terminal
    # Exécution du calcul d'addition
    resultat = addition(nombre1, nombre2)
    # Affichage du résultat formatté dans la console
    print(f"L'addition de {nombre1} et {nombre2} donne : {resultat}")


if __name__ == "__main__":
    # Point d'entrée principal du script
    # Commentaire clair : Lancement de la routine de test affichant l'addition en console
    main()
