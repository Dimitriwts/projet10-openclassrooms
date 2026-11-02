# My Content : recommandation d'articles en serverless

Projet 10 du parcours AI Engineer d'OpenClassrooms : "Réalisez une application de recommandation de contenu".

My Content est une start-up qui veut encourager la lecture. La fonctionnalité prioritaire de son MVP (première
version minimale du produit) est : "En tant qu'utilisateur de l'application, je vais recevoir une sélection de
cinq articles." Ce dépôt contient tout ce qui permet de la faire fonctionner de bout en bout :

- le notebook qui compare plusieurs systèmes de recommandation et produit le fichier du modèle ;
- l'Azure Function qui renvoie les 5 articles recommandés pour un utilisateur ;
- une application Streamlit de démonstration qui appelle cette Function.

## Architecture

On a retenu la deuxième architecture proposée par Julien : une seule Azure Function qui lit directement le
fichier du modèle dans un Blob Storage grâce au "Blob storage input binding", sans API intermédiaire.

```
Application Streamlit  --(requête HTTP : user_id)-->  Azure Function  <--(binding)--  Blob Storage
     (application/)    <--(5 identifiants d'articles)--  (azure_function/)            modeles/modele_reco.npz
```

- Azure Functions : service "serverless" de Microsoft. On ne gère aucun serveur, le code ne tourne que quand on
  l'appelle et on ne paie qu'à l'usage.
- Blob Storage : espace de stockage de fichiers dans le cloud Azure.
- Binding (liaison) : on déclare dans le code quel fichier la Function doit recevoir, et Azure le lit pour elle.

Pour prendre en compte de nouveaux utilisateurs ou de nouveaux articles, il suffit de régénérer le fichier du
modèle et de le remplacer dans le Blob Storage. La Function n'a pas besoin d'être redéployée.

Dans ce projet, la Function tourne en local avec les outils officiels de Microsoft (Azure Functions Core Tools
et l'émulateur de stockage Azurite) : l'abonnement Azure utilisé pour les projets précédents est désactivé, et
aucun nouvel essai gratuit n'est possible. Le code est celui qui serait déployé sur Azure, sans modification.

## Le système de recommandation

Les données sont celles du portail d'actualités Globo.com (jeu public Kaggle "News Portal User Interactions by
Globo.com") : environ 3 millions de clics de 322 897 utilisateurs, du 1er au 17 octobre 2017, et les
embeddings des 364 047 articles (250 nombres qui résument le contenu de chaque article).

La métrique métier est le HR@5 (taux de réussite à 5) : la part des utilisateurs qui lisent ensuite au moins
un des 5 articles proposés. Les approches sont comparées sur un découpage dans le temps : le système ne connaît
que les clics passés et doit deviner les suivants. Les réglages sont choisis sur la validation (cible : 11 et
12 octobre), puis vérifiés une seule fois sur le test (cible : à partir du 13 octobre).

| Approche | HR@5 validation | HR@5 test |
|---|---|---|
| Popularité de la dernière heure | 30,14 % | 17,79 % |
| Mélange popularité et contenu (alpha = 0,7), retenu | 30,33 % | 17,18 % |
| Filtrage par le contenu (embeddings) | 3,09 % | 1,09 % |
| Filtrage collaboratif (ALS) | 0,82 % | 0,63 % |

Chiffres issus du notebook (cellules de validation, de test et graphique récapitulatif).

Le système retenu part des 300 articles les plus lus de la dernière heure et les classe avec
`score = alpha x popularité + (1 - alpha) x similarité avec ce que l'utilisateur a déjà lu`. Un nouvel
utilisateur reçoit les articles les plus populaires.

Limite à connaître : en validation, ce mélange fait légèrement mieux que la popularité seule, mais sur le test
il fait 0,6 point de moins (écart significatif d'après le test de McNemar). Alpha est donc stocké dans le
fichier du modèle et non dans le code, pour pouvoir être ajusté sans redéploiement.

Les embeddings sont réduits de 250 à 52 valeurs par une ACP (analyse en composantes principales), qui conserve
95,1 % de l'information. Le fichier du modèle passe ainsi à 15,4 Mo au lieu des 364 Mo d'origine.

## Organisation du dépôt

```
notebooks/modelisation.ipynb      comparaison des approches, choix du modèle, export du fichier du modèle
azure_function/
    function_app.py               la Function : reçoit la requête, lit le modèle via le binding, répond
    recommandation.py             le calcul des recommandations (NumPy seul, testable sans Azure)
    host.json, requirements.txt   configuration et bibliothèques de la Function
application/app.py                application Streamlit de démonstration
requirements.txt                  bibliothèques du notebook et de l'application
```

## Reproduire le projet

Prérequis : Windows, Python 3.13, Node.js, Azure Functions Core Tools et Azure CLI.

1. Créer l'environnement Python et installer les bibliothèques :

   ```bash
   py -3.13 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Télécharger les données (archive `news-portal-user-interactions-by-globocom.zip` du lien de l'énoncé, ou
   depuis Kaggle), puis dézipper son contenu dans `data/`, et dézipper `data/clicks.zip` dans `data/clicks/`.

3. Exécuter le notebook `notebooks/modelisation.ipynb` (environ 9 minutes sur un portable sans carte graphique).
   Il crée le fichier du modèle `data/modele_reco.npz`.

4. Installer et lancer l'émulateur de stockage Azurite (à laisser tourner dans son terminal) :

   ```bash
   npm install -g azurite
   azurite --silent --location .azurite --skipApiVersionCheck
   ```

5. Dans un autre terminal, déposer le modèle dans le Blob Storage local :

   ```bash
   az storage container create -n modeles --connection-string "UseDevelopmentStorage=true"
   az storage blob upload -c modeles -n modele_reco.npz -f data/modele_reco.npz --overwrite --connection-string "UseDevelopmentStorage=true"
   ```

6. Créer le fichier `azure_function/local.settings.json`, qui dit à la Function d'utiliser Azurite (il n'est
   pas versionné car, sur Azure, il contiendrait des chaînes de connexion secrètes) :

   ```json
   {
     "IsEncrypted": false,
     "Values": {
       "FUNCTIONS_WORKER_RUNTIME": "python",
       "AzureWebJobsStorage": "UseDevelopmentStorage=true"
     }
   }
   ```

7. Lancer la Function, avec l'environnement Python activé :

   ```bash
   cd azure_function
   func start
   ```

   Elle répond sur `http://localhost:7071/api/recommandations?user_id=0`.

8. Dans un troisième terminal, environnement activé, lancer l'application :

   ```bash
   streamlit run application/app.py
   ```

Pour utiliser une Function déployée sur Azure, définir les variables d'environnement `URL_FONCTION` (adresse
de la Function, terminée par `/api`) et `CLE_FONCTION` (sa clé d'accès) avant de lancer l'application.
