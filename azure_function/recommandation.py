"""Logique de recommandation, séparée du code propre à Azure.

Ce fichier ne dépend que de NumPy : on peut le tester sur son ordinateur sans rien installer d'Azure, et
la même logique tournerait ailleurs (une API, un script) sans modification. function_app.py se contente
de recevoir la requête, d'appeler ces fonctions et de renvoyer la réponse.

Le calcul reproduit exactement l'approche "mélange" retenue dans notebooks/modelisation.ipynb :
    score = alpha x popularité + (1 - alpha) x similarité avec le profil du lecteur
"""

import io

import numpy as np


def charger_modele(contenu):
    """Lit le fichier modele_reco.npz (reçu sous forme d'octets) et renvoie ses tableaux dans un dictionnaire.

    allow_pickle=False interdit à NumPy d'exécuter du code Python caché dans le fichier : on ne lit que
    des tableaux de nombres, ce qui est plus sûr.
    """
    with np.load(io.BytesIO(contenu), allow_pickle=False) as fichier:
        return {nom: fichier[nom] for nom in fichier.files}


def historique_utilisateur(modele, user_id):
    """Articles déjà lus par l'utilisateur, ou None s'il est inconnu (nouvel utilisateur).

    Les identifiants d'utilisateurs sont triés dans le fichier : searchsorted retrouve la position par
    recherche dichotomique, sans parcourir les 322 000 utilisateurs un par un.
    """
    user_ids = modele["user_ids"]
    position = np.searchsorted(user_ids, user_id)
    if position >= len(user_ids) or user_ids[position] != user_id:
        return None
    # L'historique de l'utilisateur numéro i est rangé entre debuts[i] et debuts[i + 1]
    debut, fin = modele["debuts"][position], modele["debuts"][position + 1]
    return modele["historique"][debut:fin]


def recommander(modele, user_id, k=5):
    """Renvoie les k articles recommandés et un booléen qui dit si l'utilisateur était inconnu."""
    articles_populaires = modele["pop_articles"]
    historique = historique_utilisateur(modele, user_id)

    # Nouvel utilisateur : on ne sait rien de ses goûts, on propose les articles les plus lus du moment.
    if historique is None:
        return [int(a) for a in articles_populaires[:k]], True

    # Les embeddings ne sont stockés que pour les articles utiles, dans l'ordre des identifiants triés :
    # searchsorted donne la ligne de chaque article dans ce tableau.
    article_ids = modele["article_ids"]
    embeddings = modele["embeddings"]

    # Profil du lecteur = moyenne des embeddings des articles qu'il a lus, ramenée à une longueur de 1
    profil = embeddings[np.searchsorted(article_ids, historique)].mean(axis=0)
    profil = profil / np.linalg.norm(profil)

    # Similarité cosinus entre le profil et chaque article populaire (les embeddings sont déjà normalisés)
    similarite = embeddings[np.searchsorted(article_ids, articles_populaires)] @ profil

    alpha = float(modele["alpha"])
    score = alpha * modele["pop_scores"] + (1 - alpha) * similarite

    # Du meilleur score au moins bon, en sautant les articles déjà lus
    deja_lus = set(historique.tolist())
    recommandes = [int(a) for a in articles_populaires[np.argsort(-score)] if a not in deja_lus]
    return recommandes[:k], False
