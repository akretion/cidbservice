# Configure the poject to test

## Webhook

First you need to add a Gitlab Webook, for the merge request (MR) events since the Gitlab CI tests are triggerd by this kind of events (if the MR has been tagged with "CI" label by default, you can change the name of this trigger label in the cidbservice.con on the CI DB service host)

To add this webhook got in the project settings add choose the `Integration` submenu
- enter a full URL to access the remote CI DB service (example: https://example.com:8433)
- enter the token string (use only letters and digits) of the CI DB service, which must be also configure in the cidbservice.conf on the CI DB service host in the `service` section with the key `token`
- select only the checkbox "merge requests event" 

Documentation on Gitlab webhooks: https://docs.gitlab.com/ce/user/project/integrations/webhooks.html

## CI / CD Settings
In the settings menu of the gitlab project for which you need to addthe continuous integration tests select the submenu `CI / CD Settings` then add in the variables you must add 2 varialbes (with names and values):

- *CI_DB_SERVICE_URL*: with a full URL to access the remote CI DB service (example: https://example.com:8433)
- *CI_DB_SERVICE_TOKEN*: the token string (use only letters and digits) of the CI DB service, which must be also configure in the cidbservice.conf on the CI DB service host in the `service` section with the key `token`

## Add a file .gitlab-config.yml

Add at the root of the project the `.gitlab-config.yml` file and customize the script to run various tests, below a minimalist example:

````yaml
test:
  script:
    - export "TOKEN_HEADER=X-Gitlab-Token:$CI_DB_SERVICE_TOKEN"
    - export CURL_PARAMS="--max-time 3600 -ksf -H $TOKEN_HEADER"
    - export $(curl $CURL_PARAMS $CI_DB_SERVICE_URL/get_db/$CI_COMMIT_SHA || echo SYNTAX_TEST=1)
    - test "$SYNTAX_TEST" && echo "syntax check" || echo "full test with db $DB_NAME"
    - test "$DB_NAME" && curl $CURL_PARAMS $CI_DB_SERVICE_URL/drop_db/$DB_NAME
````

Documentation on Gitlab CI/CD : https://docs.gitlab.com/ce/ci/quick_start/

## Debug

CIDBservice tourne avec 2 services dans 2 conteneurs distincts lancés par docker-compose:
- cidbservice: qui gère les webservices (API rest), est qui délègue les tâches au service celery (ci-dessous)
- celery: qui est utilisé pour lancer les taches chronophages (de fond) comme la recréation des spares (création de base de données)

Le code de ce service est mutualisé dans le même fichier python.

En cas de problème le débuggage est compliqué car les 2 services sont interdépendants.

### Pour debbuger le cidbservice:

il faut commmenter dans le fichier docker-compose.yml dans la section cidbservice la section entrypoint
et lancer le service:
```
docker-compose run --service-ports cidbservice bash
```

Une fois le service lancé dans la console
```
flask run --host 0.0.0.0 -p 54320
``

### Pour debbuger celery:

Le debug est plus compliqué car aucun shell interactif est disponible
il faut utiliser un remote pdb:
Le port de debug est variable est exposé par une plage 6900-6999 dans le fichier docker-compose.yml
ainsi que les variable d'environement:
```
CELERY_RDB_HOST=0.0.0.0
CELERY_RDB_PORT=6900
```

Pour avoir le remote debug il faut insérer dans le code à examiner les lignes:
```
from celery.contrib import rdb
rdb.set_trace()
```

Il faut ensuite regarder les logs docker-compose de l'application
```
docker-compose logs -f celery
```

Quand le code arrive sur ces ligne il apparaît dans les instructions pour se connecter au remote debugger
Example:
``̀
Remote Debugger:6904: Ready to connect: telnet 0.0.0.0 6904
```

Il faut se connecter depuis un terminal standard pas byobu par exemple, pour que la saisie soit non bugger.
