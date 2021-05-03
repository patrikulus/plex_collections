#!/usr/bin/env python3

import re
import os
import yaml
import requests
import json
import click
import hashlib
import pprint as pretty
import urllib.parse as parse
import logging
from plexapi.server import PlexServer
from tmdbv3api import TMDb, Collection, Movie
from tmdbv3api import Configuration as TMDBConfiguration
from progress.bar import Bar

CONFIG_FILE = 'config.yaml'
IMAGE_ITEM_LIMIT = 1
DEFAULT_AREAS = ['posters', 'backgrounds', 'summaries']
DEBUG = False
DRY_RUN = False
FORCE = False
LIBRARY_IDS = False
CONFIG = dict()
TMDB = TMDb()


def init(debug=False, dry_run=False, force=False, library_ids=False):
    global DEBUG
    global DRY_RUN
    global FORCE
    global LIBRARY_IDS
    global CONFIG
    global TMDB

    DEBUG = debug
    DRY_RUN = dry_run
    FORCE = force
    LIBRARY_IDS = library_ids

    if not DEBUG:
        logging.getLogger('tmdbv3api.tmdb').disabled = True

    with open(CONFIG_FILE, 'r') as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    CONFIG['headers'] = {'X-Plex-Token': CONFIG['plex_token'], 'Accept': 'application/json'}
    CONFIG['plex_images_url'] = '%s/library/metadata/%%s/%%s?url=%%s' % CONFIG['plex_url']
    CONFIG['plex_images_upload_url'] = '%s/library/metadata/%%s/%%s?includeExternalMedia=1' % CONFIG['plex_url']
    CONFIG['plex_summary_url'] = '%s/library/sections/%%s/all?type=18&id=%%s&summary.value=%%s' % CONFIG['plex_url']

    TMDB.api_key = CONFIG['tmdb_key']
    TMDB.wait_on_rate_limit = True
    TMDB.language = 'en'

    if DEBUG:
        print('CONFIG: ')
        pretty.pprint(CONFIG)


def setup():
    try:
        data = dict()
        data['plex_url'] = click.prompt('Please enter your Plex URL', type=str)
        data['plex_token'] = click.prompt('Please enter your Plex Token', type=str)
        data['tmdb_key'] = click.prompt('Please enter your TMDB API Key', type=str)

        data['local_poster_filename'] = click.prompt(
            'Please enter the Local Poster filename (OPTIONAL)',
            default="movieset-poster",
            type=str
        )

        data['custom_poster_filename'] = click.prompt(
            'Please enter the Custom Poster filename (OPTIONAL)',
            default="movieset-poster-custom",
            type=str
        )

        data['local_art_filename'] = click.prompt(
            'Please enter the Local Background filename (OPTIONAL)',
            default="movieset-background",
            type=str
        )

        data['custom_art_filename'] = click.prompt(
            'Please enter the Custom Poster filename (OPTIONAL)',
            default="movieset-background-custom",
            type=str
        )

        with open(CONFIG_FILE, 'w') as outfile:
            yaml.dump(data, outfile, default_flow_style=False)
    except (KeyboardInterrupt, SystemExit):
        raise


def update(areas):
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_IDS and int(plex_section.key) not in LIBRARY_IDS:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = plex_section.collection()

        # Set TMDB language for section
        TMDB.language = plex_section.language

        for k, plex_collection in enumerate(plex_collections):
            print('\r\n> %s [%s/%s]' % (plex_collection.title, k + 1, len(plex_collections)))

            if 'titleSort' in plex_collection._data.attrib:
                if plex_collection._data.attrib['titleSort'].endswith('***'):
                    print('Skipping. (Skip marker found)')
                    continue

            if 'posters' in areas:
                update_poster(plex_collection)

            if 'backgrounds' in areas:
                update_background(plex_collection)

            if 'summaries' in areas:
                update_summary(plex_collection)


def list_libraries():
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))


def update_summary(plex_collection):
    if not FORCE and plex_collection.summary.strip() != '':
        print('Summary exists.')
        if DEBUG:
            print(plex_collection.summary)
        return

    summary = get_tmdb_summary(plex_collection)

    if not summary:
        print('No summary available.')
        return

    if DRY_RUN:
        print("Would update summary With: " + summary)
        return True

    requests.put(CONFIG['plex_summary_url'] %
                 (plex_collection.librarySectionID, plex_collection.ratingKey, parse.quote(summary)),
                 data={}, headers=CONFIG['headers'])
    print('Summary updated.')


def get_tmdb_summary(plex_collection_movies):
    tmdb_collection_id = get_tmdb_collection_id(plex_collection_movies)
    collection = Collection().details(collection_id=tmdb_collection_id)
    return collection.entries.get('overview')


def update_poster(plex_collection):
    update_image(plex_collection, 'posters')

def update_background(plex_collection):
    update_image(plex_collection, 'arts')

def update_image(plex_collection, metadata_type):
    for image_type in ['custom', 'local']:
        for movie in plex_collection.children:
            if check_images(movie, plex_collection.ratingKey, image_type, metadata_type):
                return

    check_for_default_image(plex_collection, metadata_type)

def check_images(movie, plex_collection_id, image_type, metadata_type):
    for media in movie.media:
        for media_part in media.parts:
            if check_image(media_part, image_type, plex_collection_id, metadata_type):
                return True

def check_image(media_part, image_type, plex_collection_id, metadata_type):
    file_path = str(os.path.dirname(media_part.file)) + os.path.sep + str(CONFIG[image_type + '_%s_filename' % singularize(metadata_type)])
    image_path = ''

    if os.path.isfile(file_path + '.jpg'):
        image_path = file_path + '.jpg'
    elif os.path.isfile(file_path + '.png'):
        image_path = file_path + '.png'

    if image_path != '':
        if DEBUG:
            print("%s Collection %s exists" % image_type, singularize(metadata_type))
        key = get_sha1(image_path)
        image_exists = check_if_image_is_uploaded(key, plex_collection_id, metadata_type)

        if image_exists:
            print("Using %s collection %s" % image_type, singularize(metadata_type))
            return True

        if DRY_RUN:
            print("Would set %s collection %s: %s" % (image_type, singularize(metadata_type), image_path))
            return True

        requests.post(CONFIG['plex_images_upload_url'] % (plex_collection_id, metadata_type),
                      data=open(image_path, 'rb'), headers=CONFIG['headers'])
        print(image_type.capitalize() + " collection %s set" % metadata_type)
        return True

def check_if_image_is_uploaded(key, plex_collection_id, metadata_type):
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, metadata_type, ''))
    key_prefix = 'upload://%s/' % metadata_type
    for image in images.get('Metadata'):
        if image.get('selected'):
            if image.get('ratingKey') == key_prefix + key:
                return True
        if image.get('ratingKey') == key_prefix + key:
            if DRY_RUN:
                print("Would change selected %s to: " % singularize(metadata_type) + image.get('ratingKey'))
                return True

            requests.put(CONFIG['plex_images_url'] % (plex_collection_id, singularize(metadata_type), image.get('ratingKey')),
                         data={}, headers=CONFIG['headers'])
            return True

def check_for_default_image(plex_collection, metadata_type):
    plex_collection_id = plex_collection.ratingKey
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, metadata_type, ''))
    first_non_default_image = ''

    if int(images.get('size')) > 0:
        for image in images.get('Metadata'):
            if image.get('selected') and image.get('ratingKey') != 'default://':
                print(("%s exists." % singularize(metadata_type)).capitalize())
                return True
            if first_non_default_image == '' and image.get('ratingKey') != 'default://':
                first_non_default_image = image.get('ratingKey')

        if first_non_default_image != '':
            print('Default Plex generated %s detected' % singularize(metadata_type))

            if DRY_RUN:
                print("Would change selected %s to: " % singularize(metadata_type) + first_non_default_image)
                return True

            requests.put(CONFIG['plex_images_url'] % (plex_collection_id, singularize(metadata_type), first_non_default_image),
                        data={}, headers=CONFIG['headers'])
            print(("%s updated with exising file." % singularize(metadata_type)).capitalize())
            return True
    else:
        download_image(plex_collection, metadata_type)


def download_image(plex_collection, metadata_type):
    plex_collection_id = plex_collection.ratingKey
    tmdb_collection_id = get_tmdb_collection_id(plex_collection)
    tmdb_metadata_type = convert_to_tmdb(metadata_type)

    tmdb_collection_images = Collection().images(tmdb_collection_id)
    image_urls = get_image_urls(tmdb_collection_images, tmdb_metadata_type, IMAGE_ITEM_LIMIT)
    upload_images_to_plex(image_urls, plex_collection_id, metadata_type)

def convert_to_tmdb(metadata_type):
    if metadata_type == 'arts':
        return 'backdrops'
    return metadata_type

def singularize(word):
    return word[:-1]

def get_plex_data(url):
    r = requests.get(url, headers=CONFIG['headers'])
    return json.loads(r.text).get('MediaContainer')


def get_image_urls(tmdb_collection_images, image_type, artwork_item_limit):
    result = []
    base_url = TMDBConfiguration().info().images.get('base_url') + 'original'
    images = tmdb_collection_images.entries.get(image_type)

    if not images:
        return result

    for i, image in enumerate(images):
        # lower score for images that are not in the films native language or engligh
        if image['iso_639_1'] is not None and image['iso_639_1'] != 'en' and image['iso_639_1'] != TMDB.language:
            images[i]['vote_average'] = 0

        # boost the score for localized images (according to the preference)
        if image['iso_639_1'] == TMDB.language:
            images[i]['vote_average'] += 1

    sorted_result = sorted(images, key=lambda k: k['vote_average'], reverse=True)

    return list(map(lambda x: base_url + x['file_path'], sorted_result[:artwork_item_limit]))


def upload_images_to_plex(images, plex_collection_id, image_type):
    if images:
        if DRY_RUN:
            for image in images:
                print("Would upload image: " + image)
            print("Would change selected image to: " + images[-1])
            return True

        plex_selected_image = ''
        bar = Bar('  Downloading %s:' % image_type, max=len(images))

        for image in images:
            bar.next()
            requests.post(CONFIG['plex_images_url'] % (plex_collection_id, image_type, image), data={},
                          headers=CONFIG['headers'])

        bar.finish()

        # set the highest rated image as selected again
        requests.put(CONFIG['plex_images_url'] % (plex_collection_id, image_type[:-1], plex_selected_image),
                     data={}, headers=CONFIG['headers'])
        print(("%s updated with new downloaded file." % singularize(image_type)).capitalize())
    else:
        print("No %s available." % singularize(image_type))


def get_plex_image_url(plex_images_url):
    r = requests.get(plex_images_url, headers=CONFIG['headers'])
    root = json.loads(r.text)

    for child in root:
        if child.attrib['selected'] == '1':
            url = child.attrib['key']
            return url[url.index('?url=') + 5:]


def get_tmdb_collection_id(plex_collection):
    for movie in plex_collection.children:
        guid = movie.guid
        match = False

        if DEBUG:
            print('Movie guid: %s' % guid)

        if guid.startswith('com.plexapp.agents.imdb://'):  # Plex Movie agent
            match = re.search(r'tt[0-9]\w+', guid)
        elif guid.startswith('com.plexapp.agents.themoviedb://'):  # TheMovieDB agent
            match = re.search(r'[0-9]\w+', guid)

        if not match:
            continue

        movie = Movie().details(movie_id=match.group())

        if not movie.entries.get('belongs_to_collection'):
            return '-1'

        return movie.entries.get('belongs_to_collection').get('id')


def get_sha1(file_path):
    h = hashlib.sha1()

    with open(file_path, 'rb') as file:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            chunk = file.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


@click.group()
def cli():
    if not os.path.isfile(CONFIG_FILE):
        click.confirm('Configuration not found, would you like to set it up?', abort=True)
        setup()
        exit(0)
    pass


@cli.command('setup', help='Set Configuration Values')
def command_setup():
    setup()


@cli.command('run', help='Update Collection Posters, Backgrounds and/or Summaries',
             epilog="eg: plex_collections.py run posters --dry-run --library=5 --library=8")
@click.argument('area', nargs=-1)
@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--force', '-f', default=False, is_flag=True, help='Overwrite existing data.')
@click.option('--library', default=False, multiple=True, type=int,
              help='Library ID to Update (Default all movie libraries)')
def run(debug, dry_run, force, library, area):
    for a in area:
        if a not in DEFAULT_AREAS:
            raise click.BadParameter('Invalid area argument(s), acceptable values are: %s' % '|'.join(DEFAULT_AREAS))

    if not area:
        area = DEFAULT_AREAS

    init(debug, dry_run, force, library)
    print('\r\nUpdating collection %s' % ' and '.join(map(lambda x: x.capitalize(), area)))
    update(area)


@cli.command('list', help='List all Libraries')
def list_all():
    init()
    print('\r\nLibraries:')
    list_libraries()


if __name__ == "__main__":
    cli()
