#!/bin/bash

REGION=$1
PLAYBACK_URL=$2

INTANCES_PER_REGION=4
NUMBER_OF_VIEWERS=300
DELAY_BETWEEN_VIEWERS=1000
TIME=$(($NUMBER_OF_VIEWERS * $DELAY_BETWEEN_VIEWERS / 1000 + 10))
SLEEP_TIME=$(($TIME + 300))

BASE_INSTANCE_NAME="${REGION}-load-testing"
PROJECTS=(livepeer-loadtest-0 livepeer-loadtest-1 livepeer-loadtest-2 livepeer-loadtest-3)
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

# Start instances
for N in $(seq 1 ${INTANCES_PER_REGION}); do
    PROJECT=${PROJECTS[N%4]}
    INSTANCE_NAME="${BASE_INSTANCE_NAME}-${N}"
    gcloud beta compute instances create ${INSTANCE_NAME} --project=${PROJECT} --zone=${ZONE} --machine-type=e2-standard-8 --network-interface=network-tier=PREMIUM,subnet=default --image=loadtesting20092022 --image-project=livepeerjs-231617
done
sleep 30

# Start Load Test
for N in $(seq 1 ${INTANCES_PER_REGION}); do
    PROJECT=${PROJECTS[N%4]}
    INSTANCE_NAME="${BASE_INSTANCE_NAME}-${N}"
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command='mkdir -p $HOME/output; rm -r $HOME/output/*'
    gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME}  --project ${PROJECT} --command="ulimit -c unlimited; ulimit -n 9999; MistLoadTest -o output -n ${NUMBER_OF_VIEWERS} -t ${TIME} -d ${DELAY_BETWEEN_VIEWERS} -g 6 ${PLAYBACK_URL} > output/logs.txt  2>&1" &
done
sleep ${SLEEP_TIME}

# Copy results and delete instances
for N in $(seq 1 ${INTANCES_PER_REGION}); do
    PROJECT=${PROJECTS[N%4]}
    INSTANCE_NAME="${BASE_INSTANCE_NAME}-${N}"
    gcloud compute scp --recurse --zone ${ZONE} --project ${PROJECT} ${INSTANCE_NAME}:output ./${REGION}-output-${N}
    gcloud compute instances delete --zone ${ZONE} ${INSTANCE_NAME} --project ${PROJECT}
done