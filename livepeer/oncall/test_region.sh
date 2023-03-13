#/bin/bash
docker run --rm -it \
    -v "$LP_TEST_VIDEO":/usr/data/videos/test.mp4 \
    livepeer/loadtester ./loadtester \
    --file=/usr/data/videos/test.mp4 \
    --api-token=$LP_API_KEY \
    --test-dur=60000h \
    --sim=1 \
    -v=4 \
    --api-server=$LP_REGION.livepeer.com \
    --wait-for-target=60m \
    --rtmp-template=rtmp://$LP_REGION-rtmp.livepeer.com/live/%s \
    --hls-template=https://$LP_REGION-playback.lp-playback.studio/hls/%s/index.m3u8
