"""
Module fournissant une fonction récursive pour calculer la racine carrée d'un nombre
en utilisant la méthode de Héron (méthode de Newton-Raphson).
"""

import math


def recursive_sqrt(n: float, x: float = None, epsilon: float = 1e-10) -> float:
    """
    Calcule la racine carrée d'un nombre de manière récursive en utilisant la méthode de Héron.

    Parameters:
    -----------
    n : float
        Le nombre non négatif dont on veut calculer la racine carrée.
    x : float, optional
        L'estimation actuelle de la racine carrée. Si None, l'estimation initiale est fixée.
    epsilon : float, optional
        La tolérance de précision pour la convergence. Par défaut 1e-10.

    Returns:
    --------
    float
        La valeur approximative de la racine carrée de n.

    Raises:
    -------
    ValueError
        Si n est strictement négatif.
    """
    if n < 0:
        raise ValueError("La racine carrée d'un nombre négatif n'est pas définie dans les nombres réels.")

    if n == 0:
        return 0.0

    if x is None:
        x = n / 2.0 if n >= 1.0 else 1.0

    next_x = 0.5 * (x + n / x)

    if abs(next_x - x) < epsilon:
        return next_x

    return recursive_sqrt(n, next_x, epsilon)


if __name__ == "__main__":
    test_values = [0, 1, 2, 9, 16, 25, 0.25, 10000]
    print("--- Tests de la fonction recursive_sqrt ---")
    for val in test_values:
        res = recursive_sqrt(val)
        expected = math.sqrt(val)
        print(f"sqrt({val:<7}) = {res:.10f} (math.sqrt = {expected:.10f}, diff = {abs(res - expected):.2e})")
