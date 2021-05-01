#escape=`
FROM rackspacedot/python37:latest

ENV CUSTOM_POSTER_FILENAME=movieset-poster-custom
ENV LOCAL_POSTER_FILENAME=movieset-poster
ENV PLEX_URL=http://localhost:32400
ENV PLEX_TOKEN=""
ENV SCAN_INTERVAL=300

WORKDIR /

RUN git clone https://github.com/patrikulus/plex_collections.git

WORKDIR /plex_collections
RUN pip install -r requirements.txt

COPY run.sh .
RUN chmod +x ./run.sh

ENTRYPOINT ./run.sh