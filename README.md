# Configure the poject to test

## Webhook

First you need to add a Gitlab Webook, for the merge request (MR) events since the Gitlab CI tests are triggerd by this kind of events (if the MR has been tagged with "CI" label by default, you can change the name of this trigger label in the cidbservice.con on the CI DB service host)

To add this webhook got in the project settings add choose the `Integration` submenu
- enter a full URL to access the remote CI DB service (example: https://example.com:8433)
- enter the token string (use only letters and digits) of the CI DB service, which must be also configure in the cidbservice.conf on the CI DB service host in the `service` section with the key `token`
- select only the checkbox "merge requests event" 

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
