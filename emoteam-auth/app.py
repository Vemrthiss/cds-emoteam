from aiohttp import ClientSession
from flask import Flask, redirect, session, request, jsonify
from flask_cors import CORS
import spotipy
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
import json

app = Flask(__name__)
load_dotenv()
CORS(app)
app.secret_key = os.urandom(24)

authorization_endpoint = "https://accounts.spotify.com/authorize"
token_endpoint = "https://accounts.spotify.com/api/token"
redirect_uri = f"{os.environ.get('API_URL')}/callback"
scope = 'user-read-recently-played'

spotify_client_id = os.environ.get('SPOTIFY_CLIENT_ID')
spotify_client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
app_url = os.environ.get('APP_URL')
functions_url = os.environ.get('FUNCTIONS_URL')


@app.route('/check-token')
def check_token():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        access_token = auth_header.split(' ')[1]
        # Create a temporary Spotify client with this token
        sp_temp = spotipy.Spotify(auth=access_token)
        try:
            # Attempt a simple request to check if the token is valid
            sp_temp.current_user()
            # If this request succeeds, the token is valid
            return jsonify(valid=True)
        except spotipy.SpotifyException as e:
            # If there's an exception, assume the token is invalid or expired
            return jsonify(valid=False, error=str(e)), 401
    else:
        return jsonify(valid=False, error="Authorization header missing"), 400


@app.route('/')
def verify():
    sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id=spotify_client_id,
                                           client_secret=spotify_client_secret,
                                           redirect_uri=redirect_uri,
                                           scope=scope)
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id=spotify_client_id,
                                           client_secret=spotify_client_secret,
                                           redirect_uri=redirect_uri,
                                           scope=scope)
    # session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)

    # Saving the access token along with all other token related info
    # session["token_info"] = token_info

    return redirect(f'{app_url}?code={token_info["access_token"]}')

@app.route('/get-user')
def get_user():
    auth_header = request.headers.get('Authorization')
    if auth_header:
        token = auth_header.split(" ")[1]
    else:
        return jsonify({"error": "Authorization header is missing"}), 401

    sp = spotipy.Spotify(auth=token)
    user = sp.current_user()
    return jsonify(user)


@app.route('/get-recent', methods=['POST'])
def get_recent():
    auth_header = request.headers.get('Authorization')
    if auth_header:
        token = auth_header.split(" ")[1]
    else:
        return jsonify({"error": "Authorization header is missing"}), 401

    sp = spotipy.Spotify(auth=token)
    data = request.get_json()
    try:
        recently_played = sp.current_user_recently_played(limit=data.get('limit', 20), after=data.get('after'))
        payloads = []
        unique_ids = set()  # remove duplicates
        print('items length', len(recently_played['items']))
        for item in recently_played['items']:
            preview_url = item['track']['preview_url']
            if preview_url is None:
                continue
            track_id = item["track"]["id"]
            if track_id not in unique_ids:
                unique_ids.add(track_id)
                payloads.append({
                    'preview_url': preview_url,
                    'track_id': track_id,
                    'track_name': item["track"]["name"]
                })

        result = asyncio.run(get_recent_http(payloads))
        # print(result)
        temp = []
        for item in result:
            try:
                decoded = item.decode('utf-8')
                temp.append(json.loads(decoded))
            except Exception as e:
                print(e)
        # make sure to return the non-lowercased track ids to app
        resp = list(
            filter(lambda track: any(d['track_id'].lower() == track['track_id'].lower() for d in temp), payloads)
        )
        print('resp', len(resp))
        return jsonify(resp)
    except spotipy.SpotifyException as e:
        return jsonify({"error": str(e)}), 400


@app.route('/predict', methods=['POST'])
def predict():
    auth_header = request.headers.get('Authorization')
    if auth_header:
        token = auth_header.split(" ")[1]
    else:
        return jsonify({"error": "Authorization header is missing"}), 401

    sp = spotipy.Spotify(auth=token)
    data = request.get_json()
    user = sp.current_user()
    if user is None:
        return jsonify({"error": "Could not obtain user info from spotify via token"}), 500
    user_id = user["id"]
    payloads = [{
        'user_id': user_id,
        'track_id': track_id
    } for track_id in data]
    result = asyncio.run(make_predictions(payloads))
    print(result)
    temp = []
    for item in result:
        try:
            decoded = item.decode('utf-8')
            temp.append(json.loads(decoded))
        except Exception as e:
            print(e)
    resp = list(
        filter(lambda pred: any(d['track_id'].lower() == pred['track_id'].lower() for d in payloads), temp)
    )
    return jsonify(resp)


timeout_config = aiohttp.ClientTimeout(
    total=None
)
client_config = dict(trust_env=True, timeout=timeout_config)


async def get_recent_http(payloads):
    async with aiohttp.ClientSession(**client_config) as sess:
        return await asyncio.gather(
            *(do_post_parallel(f'{functions_url}/process_mp3', sess, payload) for payload in payloads))


async def make_predictions(payloads):
    async with aiohttp.ClientSession(**client_config) as sess:
        return await asyncio.gather(
            *(do_post_parallel(f'{functions_url}/predict', sess, payload) for payload in payloads))


async def do_post_parallel(url, sess: ClientSession, payload):
    try:
        async with sess.post(url=url, json=payload) as response:
            return await response.read()
    except Exception as e:
        print("Unable to get url {} due to {}.".format(url, e.__class__))


# def get_token(sess):
#     token_valid = False
#     token_info = sess.get("token_info", {})
#
#     # Checking if the session already has a token stored
#     if not (sess.get('token_info', False)):
#         token_valid = False
#         return token_info, token_valid
#
#     # Checking if token has expired
#     now = int(time.time())
#     is_token_expired = sess.get('token_info').get('expires_at') - now < 60
#
#     # Refreshing token if it has expired
#     if is_token_expired:
#         sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id=spotify_client_id,
#                                                client_secret=spotify_client_secret,
#                                                redirect_uri=redirect_uri,
#                                                scope=scope)
#         token_info = sp_oauth.refresh_access_token(sess.get('token_info').get('refresh_token'))
#
#     token_valid = True
#     return token_info, token_valid


# TODO: make sure the correct app.run is used
if __name__ == '__main__':
    # DEV
    # app.run(host='0.0.0.0', port=3000)

    # PROD
    app.run()
