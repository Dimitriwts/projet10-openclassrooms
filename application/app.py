"""Application de démonstration My Content (Streamlit).

Streamlit est une bibliothèque Python qui transforme un script en page web interactive, sans écrire de
HTML ni de JavaScript. On l'utilise ici pour montrer le système de recommandation à Samia.

L'application ne contient aucune donnée ni aucun modèle : elle se contente d'appeler l'Azure Function,
comme le ferait la future application mobile. Elle :
1. récupère une liste d'identifiants d'utilisateurs (adresse /api/utilisateurs de la Function) ;
2. laisse choisir un utilisateur, ou saisir un identifiant inconnu pour voir le cas d'un nouvel utilisateur ;
3. appelle la Function pour cet identifiant et affiche les 5 articles recommandés, avec ce que le lecteur
   a déjà lu et, pour chaque article, les raisons du choix (popularité, ressemblance, catégorie).

Lancement : streamlit run application/app.py (la Function doit tourner, voir le README).
"""

import os

import pandas as pd
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


def nombre(x, decimales=2):
    """Nombre à virgule écrit à la française (0,62 plutôt que 0.62)."""
    return f"{x:.{decimales}f}".replace(".", ",")


def lectures(n):
    """« 1 lecture », « 2 lectures » : accorde le mot au nombre."""
    return f"{n} lecture{'s' if n > 1 else ''}"


def explication(article, nouvel_utilisateur):
    """Une phrase qui dit pourquoi cet article a été choisi, à partir des chiffres renvoyés par la Function."""
    rang = article["rang_popularite"]
    phrase = (
        f"{rang}{'er' if rang == 1 else 'e'} article le plus lu de la dernière heure "
        f"({article['clics_derniere_heure']} clics), publié il y a {nombre(article['age_heures'], 0)} h"
    )
    if nouvel_utilisateur:
        return phrase + "."
    deja = article["lectures_meme_categorie"]
    categorie = (
        f"catégorie {article['categorie']} déjà lue {deja} fois par ce lecteur"
        if deja else f"catégorie {article['categorie']} jamais lue par ce lecteur"
    )
    return f"{phrase} ; {categorie} ; ressemblance avec ses lectures : {nombre(article['similarite'])}."


st.set_page_config(page_title="My Content : recommandations", layout="wide")
st.title("My Content : vos 5 articles du moment")

with st.expander("Comment sont choisis les articles ?", expanded=False):
    st.markdown(
        """
Les données viennent du portail d'actualités Globo.com : qui a cliqué sur quel article, et quand
(du 1er au 17 octobre 2017). Pour chaque article on connaît seulement son numéro, sa catégorie (un numéro,
sans nom), sa date de publication, son nombre de mots et son embedding : une liste de nombres qui résume
son contenu. Les titres et les textes ne sont pas fournis, c'est pourquoi les articles sont désignés par
leur numéro.

La sélection se fait en trois temps :
1. on prend les 300 articles les plus lus pendant la dernière heure (l'actualité du moment) ;
2. on donne à chacun un score : 70 % pour sa popularité, 30 % pour sa ressemblance avec ce que le lecteur
   a déjà lu ;
3. on retire ceux qu'il a déjà lus et on garde les 5 meilleurs scores.

Un nouveau lecteur, dont on ne connaît aucune lecture, reçoit simplement les articles les plus lus.

Comment lire les colonnes : la popularité et la ressemblance vont de 0 à 1. Une popularité de 1 est
l'article le plus lu de la dernière heure. Une ressemblance proche de 1 veut dire "même sujet que ce
qu'il lit d'habitude", proche de 0 "sans rapport".
"""
    )

try:
    utilisateurs = liste_utilisateurs()
except requests.RequestException as erreur:
    st.error(f"Impossible de joindre la Function à l'adresse {URL_FONCTION}. Est-elle lancée ?\n\n{erreur}")
    st.stop()

colonne_liste, colonne_saisie = st.columns(2)
choix = colonne_liste.selectbox("Choisissez un lecteur", utilisateurs)
saisie = colonne_saisie.text_input("Ou saisissez un autre identifiant (par exemple 999999 pour un nouveau lecteur)")

# Un identifiant saisi à la main est prioritaire sur la liste déroulante
if saisie.strip():
    if not saisie.strip().isdigit():
        st.warning("L'identifiant doit être un nombre entier.")
        st.stop()
    user_id = int(saisie.strip())
else:
    user_id = choix

if not st.button("Recommander"):
    st.stop()

try:
    resultat = appeler("recommandations", user_id=user_id)
except requests.RequestException as erreur:
    st.error(f"La Function n'a pas pu répondre : {erreur}")
    st.stop()

parametres = resultat["parametres"]
lecteur = resultat["lecteur"]
nouvel_utilisateur = resultat["nouvel_utilisateur"]

# 1. Ce que l'on sait du lecteur
st.header(f"Le lecteur {user_id}")
if nouvel_utilisateur:
    st.info("Ce lecteur n'a encore rien lu : on ne connaît pas ses goûts, on lui propose l'actualité du moment.")
else:
    a, b = st.columns(2)
    a.metric("Articles déjà lus", lecteur["nb_lectures"])
    b.metric("Catégorie qu'il lit le plus", f"n° {lecteur['categories_frequentes'][0]['categorie']}")
    frequentes = ", ".join(
        f"n° {c['categorie']} ({lectures(c['nb_lectures'])})" for c in lecteur["categories_frequentes"]
    )
    st.write(f"Ses catégories préférées : {frequentes}.")
    st.write("Ses 5 dernières lectures :")
    # L'âge n'est pas affiché ici : calculé à la date de référence, il ne dirait rien du moment de la lecture
    st.dataframe(
        pd.DataFrame(lecteur["dernieres_lectures"]).drop(columns=["age_heures"]).rename(columns={
            "article_id": "Article", "categorie": "Catégorie", "publie_le": "Publié le (UTC)", "nb_mots": "Mots",
        }),
        hide_index=True,
    )

# 2. La règle appliquée, avec les vrais paramètres renvoyés par la Function
st.header("Comment la sélection est faite")
alpha = parametres["alpha"]
st.write(
    f"Parmi les {parametres['nb_candidats']} articles les plus lus pendant la dernière "
    f"{'heure' if parametres['fenetre_popularite_heures'] == 1 else str(parametres['fenetre_popularite_heures']) + ' heures'} "
    f"(\"maintenant\" = {parametres['maintenant']} UTC, fin des données), chaque article reçoit le score "
    f"**{nombre(alpha)} × popularité + {nombre(1 - alpha)} × ressemblance**, puis on garde les 5 meilleurs "
    "que le lecteur n'a pas encore lus."
)

# 3. Les 5 articles et les raisons du choix
st.header("Les 5 articles recommandés")
for rang, article in enumerate(resultat["recommandations"], start=1):
    st.markdown(f"**{rang}. Article n° {article['article_id']}** : {explication(article, nouvel_utilisateur)}")

tableau = pd.DataFrame(resultat["recommandations"]).rename(columns={
    "article_id": "Article", "categorie": "Catégorie", "publie_le": "Publié le (UTC)",
    "age_heures": "Âge (h)", "nb_mots": "Mots", "rang_popularite": "Rang popularité",
    "clics_derniere_heure": "Clics dernière heure", "popularite": "Popularité (0 à 1)",
    "similarite": "Ressemblance (0 à 1)", "score": "Score",
    "lectures_meme_categorie": "Lectures dans cette catégorie",
})
if nouvel_utilisateur:
    tableau = tableau.drop(columns=["Ressemblance (0 à 1)", "Lectures dans cette catégorie"])
st.dataframe(tableau, hide_index=True)
