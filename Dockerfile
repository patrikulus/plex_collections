#escape=`
FROM rackspacedot/python37:latest

ENV CUSTOM_POSTER_FILENAME=movieset-poster-custom
ENV LOCAL_POSTER_FILENAME=movieset-poster
ENV CUSTOM_ART_FILENAME=movieset-background-custom
ENV LOCAL_ART_FILENAME=movieset-background
ENV PLEX_URL=http://localhost:32400
ENV PLEX_TOKEN=""
ENV SCAN_INTERVAL=300

WORKDIR /plex_collections
COPY plex_collections.py requirements.txt run.sh ./

RUN pip install -r requirements.txt
RUN chmod +x plex_collections.py run.sh

ENTRYPOINT ./run.sh