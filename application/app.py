"""Application de démonstration My Content (Streamlit).

Streamlit est une bibliothèque Python qui transforme un script en page web interactive, sans écrire de
HTML ni de JavaScript. On l'utilise ici pour montrer le système de recommandation à Samia.

L'application ne contient aucune donnée ni aucun modèle : elle se contente d'appeler l'Azure Function,
comme le ferait la future application mobile. Elle :
1. récupère une liste d'identifiants d'utilisateurs (adresse /api/utilisateurs de la Function) ;
2. laisse choisir un utilisateur, ou saisir un identifiant inconnu pour voir le cas d'un nouvel utilisateur ;
3. appelle la Function pour cet identifiant et affiche les 5 articles recommandés.

Lancement : streamlit run application/app.py (la Function doit tourner, voir le README).
"""

import os

import requests
import streamlit as st

# Adresse de la Function. Par défaut, la Function lancée en local avec "func start".
# Une fois déployée sur Azure, il suffirait de définir la variable d'environnement URL_FONCTION
# (et CLE_FONCTION, la clé secrète exigée par Azure) sans toucher au code.
URL_FONCTION = os.environ.get("URL_FONCTION", "http://localhost:7071/api")
CLE_FONCTION = os.environ.get("CLE_FONCTION", "")

# Au-delà de 10 secondes sans réponse, on abandonne plutôt que de laisser la page bloquée
DELAI_MAX = 10


def appeler(route, **parametres):
    """Appelle une adresse de la Function et renvoie sa réponse JSON (un dictionnaire Python)."""
    if CLE_FONCTION:
        parametres["code"] = CLE_FONCTION  # paramètre attendu par Azure pour la clé secrète
    reponse = requests.get(f"{URL_FONCTION}/{route}", params=parametres, timeout=DELAI_MAX)
    reponse.raise_for_status()  # déclenche une erreur si la Function a répondu par un code d'échec
    return reponse.json()


# La liste des utilisateurs ne change pas pendant la démonstration : st.cache_data garde la réponse
# en mémoire pour ne pas rappeler la Function à chaque clic.
@st.cache_data
def liste_utilisateurs():
    return appeler("utilisateurs", n=100)["user_ids"]


st.set_page_config(page_title="My Content : recommandations")
st.title("My Content : vos 5 articles du moment")

try:
    utilisateurs = liste_utilisateurs()
except requests.RequestException as erreur:
    st.error(f"Impossible de joindre la Function à l'adresse {URL_FONCTION}. Est-elle lancée ?\n\n{erreur}")
    st.stop()

choix = st.selectbox("Choisissez un utilisateur", utilisateurs)
saisie = st.text_input("Ou saisissez un autre identifiant (par exemple 999999 pour un nouvel utilisateur)")

# Un identifiant saisi à la main est prioritaire sur la liste déroulante
if saisie.strip():
    if not saisie.strip().isdigit():
        st.warning("L'identifiant doit être un nombre entier.")
        st.stop()
    user_id = int(saisie.strip())
else:
    user_id = choix

if st.button("Recommander"):
    try:
        resultat = appeler("recommandations", user_id=user_id)
    except requests.RequestException as erreur:
        st.error(f"La Function n'a pas pu répondre : {erreur}")
        st.stop()

    if resultat["nouvel_utilisateur"]:
        st.info(
            f"L'utilisateur {user_id} n'a encore rien lu : on lui propose les articles les plus lus du moment."
        )
    else:
        st.success(
            f"Sélection personnalisée pour l'utilisateur {user_id} : articles populaires du moment, "
            "classés selon leur ressemblance avec ce qu'il a déjà lu."
        )

    for rang, article in enumerate(resultat["articles"], start=1):
        st.write(f"{rang}. Article n° {article}")
