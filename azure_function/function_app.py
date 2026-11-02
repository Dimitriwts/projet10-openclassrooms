"""Azure Function de recommandation d'articles (architecture "Blob storage input binding").

Principe : à chaque appel, Azure lit lui-même le fichier du modèle dans le Blob Storage (un espace de
stockage de fichiers dans le cloud) et le passe à la fonction. C'est le "binding" (liaison) : on déclare
quel fichier on veut, et on n'écrit aucun code de connexion au stockage. Pour mettre à jour le modèle
(nouveaux utilisateurs, nouveaux articles, autre valeur d'alpha), il suffit de remplacer le fichier dans
le Blob Storage, sans redéployer la fonction.

Deux adresses sont exposées :
- /api/recommandations?user_id=123 : les 5 articles recommandés pour cet utilisateur, avec l'explication
  de chaque choix et un résumé de ce qu'il a déjà lu ;
- /api/utilisateurs?n=100 : une liste d'identifiants d'utilisateurs, pour l'application de démonstration.
"""

import json
import logging

import azure.functions as func

from recommandation import charger_modele, recommander

# AuthLevel.FUNCTION : l'appel doit contenir une clé secrète (le paramètre "code" dans l'adresse).
# Sans elle, n'importe qui sur internet pourrait appeler la fonction et la faire tourner à nos frais.
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Emplacement du modèle : conteneur "modeles" du compte de stockage de la Function App.
# "AzureWebJobsStorage" est le nom du réglage qui contient la chaîne de connexion à ce compte ;
# Azure le crée automatiquement avec la Function App.
CHEMIN_MODELE = "modeles/modele_reco.npz"

# Piège rencontré : sans précision, le binding transmet le fichier comme du texte. Les octets qui ne
# forment pas de caractères valides sont alors remplacés, et la fonction recevait 27,8 Mo au lieu des
# 15,1 Mo du fichier, illisible ("BadZipFile"). DataType.BINARY demande les octets tels quels.
TYPE_FICHIER = func.DataType.BINARY


def reponse_json(contenu, statut=200):
    return func.HttpResponse(json.dumps(contenu), status_code=statut, mimetype="application/json")


@app.route(route="recommandations", methods=["GET"])
@app.blob_input(arg_name="fichier", path=CHEMIN_MODELE, connection="AzureWebJobsStorage",
                data_type=TYPE_FICHIER)
def recommandations(req: func.HttpRequest, fichier: func.InputStream) -> func.HttpResponse:
    # L'identifiant arrive sous forme de texte dans l'adresse : on vérifie que c'est bien un nombre
    texte = req.params.get("user_id", "")
    if not texte.isdigit():
        return reponse_json({"erreur": "Paramètre user_id manquant ou non numérique"}, 400)
    user_id = int(texte)

    modele = charger_modele(fichier.read())
    resultat = recommander(modele, user_id, k=5)
    articles = [r["article_id"] for r in resultat["recommandations"]]
    logging.info("Recommandations pour %s (nouvel utilisateur : %s) : %s",
                 user_id, resultat["nouvel_utilisateur"], articles)

    # La réponse contient les 5 articles et, pour chacun, de quoi comprendre pourquoi il a été choisi
    return reponse_json(resultat)


@app.route(route="utilisateurs", methods=["GET"])
@app.blob_input(arg_name="fichier", path=CHEMIN_MODELE, connection="AzureWebJobsStorage",
                data_type=TYPE_FICHIER)
def utilisateurs(req: func.HttpRequest, fichier: func.InputStream) -> func.HttpResponse:
    # On ne renvoie qu'une partie des 322 000 identifiants : la liste complète ferait plusieurs Mo
    # et serait inutilisable dans une liste déroulante.
    texte = req.params.get("n", "100")
    n = min(int(texte), 1000) if texte.isdigit() else 100

    modele = charger_modele(fichier.read())
    return reponse_json({"user_ids": [int(u) for u in modele["user_ids"][:n]]})
