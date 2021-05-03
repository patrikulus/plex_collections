# Update config file
echo "" > config.yaml
echo "custom_poster_filename: $CUSTOM_POSTER_FILENAME" >> config.yaml
echo "local_poster_filename: $LOCAL_POSTER_FILENAME" >> config.yaml
echo "custom_art_filename: $CUSTOM_ART_FILENAME" >> config.yaml
echo "local_art_filename: $LOCAL_ART_FILENAME" >> config.yaml
echo "plex_token: $PLEX_TOKEN" >> config.yaml
echo "plex_url: $PLEX_URL" >> config.yaml
echo "tmdb_key: $TMDB_KEY" >> config.yaml

# Run
while :
do
    python plex_collections.py run
    sleep $SCAN_INTERVAL
done