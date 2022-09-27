#!/bin/bash

CMD=$1
REGION=$2
PLAYBACK_URL=$3

NUMBER_OF_VIEWERS=300
DELAY_BETWEEN_VIEWERS=1000
TIME=$(($NUMBER_OF_VIEWERS * $DELAY_BETWEEN_VIEWERS / 1000 + 10))

INSTANCE_NAME="${REGION}-load-testing"
PROJECT="livepeerjs-231617"

case "$REGION" in
 "nyc" ) ZONE="us-east4-c";;
 "fra" ) ZONE="europe-west3-c";;
 "lon" ) ZONE="europe-west2-c";;
 "mdw" ) ZONE="us-central1-a";;
 "lax" ) ZONE="us-west2-a";;
 "sao" ) ZONE="southamerica-east1-b";;
 "sin" ) ZONE="asia-southeast1-b";;
 "prg" ) ZONE="europe-central2-a";;
 *) echo "wrong region '${REGION}'"; exit 1;;
esac

echo "using instance '${INSTANCE_NAME}' in zone '${ZONE}'"

if [ "${CMD}" == "prepare" ]; then
    gcloud compute instances start --zone ${ZONE} ${INSTANCE_NAME} --project ${PROJECT}
elif [ "${CMD}" == "patch" ]; then
    gcloud compute scp --zone ${ZONE} --project ${PROJECT} /Users/rafalleszko/Downloads/livepeer-mistserver-linux-amd64/MistLoadTest ${INSTANCE_NAME}:MistLoadTest
    gcloud compute scp --zone ${ZONE} --project ${PROJECT} /Users/rafalleszko/Downloads/livepeer-mistserver-linux-amd64/MistAnalyserHLS ${INSTANCE_NAME}:MistAnalyserHLS
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command="sudo mv MistLoadTest /usr/bin/MistLoadTest"
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command="sudo mv MistAnalyserHLS /usr/bin/MistAnalyserHLS"
elif [ "${CMD}" == "start" ]; then
    # cleanup
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command='mkdir -p $HOME/output; rm -r $HOME/output/*'

    # perform load testing
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command="ulimit -c unlimited; ulimit -n 9999; MistLoadTest -o output -n ${NUMBER_OF_VIEWERS} -t ${TIME} -d ${DELAY_BETWEEN_VIEWERS} -g 6 ${PLAYBACK_URL} > output/logs.txt  2>&1"

    # copy result files
    gcloud compute scp --recurse --zone ${ZONE} --project ${PROJECT} ${INSTANCE_NAME}:output ./${REGION}-output
elif [ "${CMD}" == "stop" ]; then
    gcloud compute instances stop --zone ${ZONE} ${INSTANCE_NAME} --project ${PROJECT}
fi