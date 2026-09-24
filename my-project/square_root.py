import math


def calculate_square_root(number: float) -> float:
    """Calcule et retourne la racine carrée d'un nombre positif ou nul.

    Args:
        number (float): Le nombre dont on souhaite calculer la racine carrée.

    Returns:
        float: La racine carrée du nombre.

    Raises:
        ValueError: Si le nombre est négatif.
    """
    if number < 0:
        raise ValueError("Impossible de calculer la racine carrée d'un nombre négatif.")
    return math.sqrt(number)


if __name__ == "__main__":
    test_values = [0, 4, 9, 16, 25, 2]
    for val in test_values:
        print(f"La racine carrée de {val} est {calculate_square_root(val)}")
