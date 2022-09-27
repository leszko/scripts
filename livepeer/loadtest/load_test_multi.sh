#!/bin/bash
set -e

REGION=$1
LIVEPEER_STUDIO_API_TOKEN=$2

INSTANCES_PER_REGION=2
SIM_STREAM_PER_INSTANCE=30
INSTANCE_NAME_PREFIX="multi-load-test"
CONTAINER_IMAGE="livepeer/loadtester:master"
DURATION_MIN=60
API_SERVER="origin.livepeer.com"
RTMP_TEMPLATE="rtmp://ingest.livepeer.studio/live/%s"
HLS_TEMPLATE='https://playback.livepeer.studio/hls/%s/index.m3u8'

PROJECT="livepeerjs-231617"
MACHINE_TYPE="e2-standard-16"
DURATION="${DURATION_MIN}m"
SLEEP_TIME=$(((${DURATION_MIN} + 10) * 60))

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

echo "Starting ${N} instances in the region '${REGION}'"
for N in $(seq 1 ${INSTANCES_PER_REGION}); do
  INSTANCE_NAME="${INSTANCE_NAME_PREFIX}-${REGION}-${N}"

    gcloud compute instances create-with-container ${INSTANCE_NAME} \
      --project=${PROJECT} \
      --zone=${ZONE} \
      --machine-type=${MACHINE_TYPE} \
      --network-interface=network-tier=PREMIUM,subnet=default \
      --maintenance-policy=MIGRATE \
      --provisioning-model=STANDARD \
      --service-account=211814034878-compute@developer.gserviceaccount.com \
      --scopes=https://www.googleapis.com/auth/devstorage.read_only,https://www.googleapis.com/auth/logging.write,https://www.googleapis.com/auth/monitoring.write,https://www.googleapis.com/auth/servicecontrol,https://www.googleapis.com/auth/service.management.readonly,https://www.googleapis.com/auth/trace.append \
      --image=projects/cos-cloud/global/images/cos-stable-85-13310-1041-9 \
      --boot-disk-size=100GB \
      --boot-disk-type=pd-ssd \
      --boot-disk-device-name=load-test-50-global \
      --container-image=${CONTAINER_IMAGE} \
      --container-restart-policy=never \
      --container-command=/root/loadtester \
      --container-arg=-file=https://eric-test-livepeer.s3.amazonaws.com/bbbx3_720.mp4 \
      --container-arg=-api-token=${LIVEPEER_STUDIO_API_TOKEN} \
      --container-arg=-test-dur=${DURATION} \
      --container-arg=-sim=${SIM_STREAM_PER_INSTANCE} \
      --container-arg=-v=4 \
      --container-arg=-api-server=${API_SERVER} \
      --container-arg=-wait-for-target=${DURATION} \
      --container-arg=-rtmp-template=${RTMP_TEMPLATE} \
      --container-arg=-hls-template=${HLS_TEMPLATE} \
      --no-shielded-secure-boot \
      --shielded-vtpm \
      --shielded-integrity-monitoring \
      --labels=container-vm=cos-stable-85-13310-1041-9
done

echo "Waiting ${SLEEP_TIME}s to complete load test in the region '${REGION}'"
sleep ${SLEEP_TIME}

echo "Fetching logs and deleting instances in the region '${REGION}'"
for N in $(seq 1 ${INSTANCES_PER_REGION}); do
  INSTANCE_NAME="${INSTANCE_NAME_PREFIX}-${REGION}-${N}"
  gcloud compute ssh --zone ${ZONE} ${INSTANCE_NAME} --project ${PROJECT} --command="docker logs \$(docker ps -a -q --filter ancestor=${CONTAINER_IMAGE})" >& ${REGION}-${N}-logs.txt
  gcloud compute instances delete ${INSTANCE_NAME} --zone ${ZONE} --quiet
done
