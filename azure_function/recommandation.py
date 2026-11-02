"""Logique de recommandation, séparée du code propre à Azure.

Ce fichier ne dépend que de NumPy : on peut le tester sur son ordinateur sans rien installer d'Azure, et
la même logique tournerait ailleurs (une API, un script) sans modification. function_app.py se contente
de recevoir la requête, d'appeler ces fonctions et de renvoyer la réponse.

Le calcul reproduit exactement l'approche "mélange" retenue dans notebooks/modelisation.ipynb :
    score = alpha x popularité + (1 - alpha) x similarité avec le profil du lecteur

En plus des articles, on renvoie de quoi comprendre le choix : pour chaque article, sa popularité, sa
ressemblance avec les lectures du lecteur et ses informations (catégorie, date, longueur) ; et un résumé
de ce que le lecteur a déjà lu. Le jeu de données n'a ni titre ni texte d'article : ce sont les seules
informations disponibles, et les catégories ne sont que des numéros.
"""

import io
from collections import Counter
from datetime import datetime, timezone

import numpy as np

HEURE_MS = 3600 * 1000  # les dates sont en millisecondes


def charger_modele(contenu):
    """Lit le fichier modele_reco.npz (reçu sous forme d'octets) et renvoie ses tableaux dans un dictionnaire.

    allow_pickle=False interdit à NumPy d'exécuter du code Python caché dans le fichier : on ne lit que
    des tableaux de nombres, ce qui est plus sûr.
    """
    with np.load(io.BytesIO(contenu), allow_pickle=False) as fichier:
        return {nom: fichier[nom] for nom in fichier.files}


def date_lisible(ms):
    """Date en millisecondes vers un texte du type 17/10/2017 14:05 (heure UTC, celle des données)."""
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%d/%m/%Y %H:%M")


def historique_utilisateur(modele, user_id):
    """Articles déjà lus par l'utilisateur, du plus ancien au plus récent, ou None s'il est inconnu.

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


def infos_article(modele, article_id):
    """Catégorie, date de publication, âge et longueur d'un article."""
    # Les articles sont rangés par identifiant croissant : searchsorted donne leur ligne
    ligne = np.searchsorted(modele["article_ids"], article_id)
    publication = modele["dates_publication"][ligne]
    return {
        "article_id": int(article_id),
        "categorie": int(modele["categories"][ligne]),
        "publie_le": date_lisible(publication),
        "age_heures": round(float(modele["maintenant"] - publication) / HEURE_MS, 1),
        "nb_mots": int(modele["nb_mots"][ligne]),
    }


def resume_lecteur(modele, historique):
    """Ce que le lecteur a déjà lu : nombre d'articles, catégories préférées, dernières lectures."""
    categories = [infos_article(modele, a)["categorie"] for a in historique]
    return {
        "nb_lectures": int(len(historique)),
        # Les 3 catégories qu'il lit le plus, avec le nombre de lectures dans chacune
        "categories_frequentes": [
            {"categorie": c, "nb_lectures": n} for c, n in Counter(categories).most_common(3)
        ],
        # Ses 5 dernières lectures, la plus récente en premier
        "dernieres_lectures": [infos_article(modele, a) for a in historique[::-1][:5]],
    }


def recommander(modele, user_id, k=5):
    """Renvoie les k articles recommandés, l'explication de chaque choix et le résumé du lecteur."""
    articles_populaires = modele["pop_articles"]
    popularite = modele["pop_scores"]  # nombre de clics divisé par celui de l'article le plus cliqué
    historique = historique_utilisateur(modele, user_id)
    nouvel_utilisateur = historique is None

    if nouvel_utilisateur:
        # On ne sait rien de ses goûts : seule compte la popularité, comme si alpha valait 1
        alpha = 1.0
        similarite = np.full(len(articles_populaires), np.nan)
        deja_lus = set()
    else:
        alpha = float(modele["alpha"])
        article_ids = modele["article_ids"]
        embeddings = modele["embeddings"]

        # Profil du lecteur = moyenne des embeddings des articles qu'il a lus, ramenée à une longueur de 1
        profil = embeddings[np.searchsorted(article_ids, historique)].mean(axis=0)
        profil = profil / np.linalg.norm(profil)

        # Similarité cosinus entre le profil et chaque article populaire (embeddings déjà normalisés).
        # Proche de 1 : même sujet que ses lectures ; proche de 0 : rien à voir.
        similarite = embeddings[np.searchsorted(article_ids, articles_populaires)] @ profil
        deja_lus = set(historique.tolist())

    score = alpha * popularite + (1 - alpha) * np.nan_to_num(similarite)

    # Du meilleur score au moins bon, en sautant les articles déjà lus
    choisis = [i for i in np.argsort(-score, kind="stable") if articles_populaires[i] not in deja_lus][:k]

    categories_lues = Counter(infos_article(modele, a)["categorie"] for a in deja_lus)
    recommandations = []
    for i in choisis:
        infos = infos_article(modele, articles_populaires[i])
        infos.update({
            "rang_popularite": int(i) + 1,  # 1 = l'article le plus lu de la dernière heure
            "clics_derniere_heure": int(modele["pop_clics"][i]),
            "popularite": round(float(popularite[i]), 3),
            "similarite": None if nouvel_utilisateur else round(float(similarite[i]), 3),
            "score": round(float(score[i]), 3),
            # Combien d'articles de la même catégorie le lecteur a déjà lus (aide à lire la similarité)
            "lectures_meme_categorie": categories_lues.get(infos["categorie"], 0),
        })
        recommandations.append(infos)

    return {
        "user_id": int(user_id),
        "nouvel_utilisateur": nouvel_utilisateur,
        "parametres": {
            "alpha": round(alpha, 2),
            "fenetre_popularite_heures": int(modele["heures_popularite"]),
            "maintenant": date_lisible(modele["maintenant"]),
            "nb_candidats": int(len(articles_populaires)),
        },
        "lecteur": None if nouvel_utilisateur else resume_lecteur(modele, historique),
        "recommandations": recommandations,
    }
