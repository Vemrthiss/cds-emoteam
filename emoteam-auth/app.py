from flask import Flask, redirect, session, request, jsonify
from flask_cors import CORS
import spotipy
import os
from dotenv import load_dotenv
import requests
import asyncio
import aiohttp
import time

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
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)

    # Saving the access token along with all other token related info
    session["token_info"] = token_info

    return redirect(f'{app_url}?code={token_info["access_token"]}')


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
        get_recent_http(recently_played)
        return jsonify(recently_played)
    except spotipy.SpotifyException as e:
        return jsonify({"error": str(e)}), 400



def get_recent_http(recently_played):
    print("recently played: ", recently_played)
    payload = [{'preview_url': item['track']['preview_url'], 'track_id': item["track"]["id"]} for item in recently_played['items']]
    print("payload: ", payload)
    azure_function_url = "http://localhost:7071/process_mp3"
    try:
        response = requests.post(azure_function_url, json=payload)
        print("HTTP response:", response.status_code)
        print("Response text:", response.text)
        return "Response received"
    except Exception as e:
        print("Error sending POST request:", str(e))
        return "Error occurred"

    
    
async def get(url, sess):
    try:
        async with sess.get(url=url) as response:
            resp = await response.read()
            print("Successfully got url {} with resp of length {}.".format(url, len(resp)))
    except Exception as e:
        print("Unable to get url {} due to {}.".format(url, e.__class__))


websites = """https://www.youtube.com
https://www.facebook.com
https://www.baidu.com
https://www.yahoo.com
https://www.amazon.com
https://www.wikipedia.org
http://www.qq.com
https://www.google.co.in
https://www.twitter.com
https://www.live.com
http://www.taobao.com
https://www.bing.com
https://www.instagram.com
http://www.weibo.com
http://www.sina.com.cn
https://www.linkedin.com
http://www.yahoo.co.jp
http://www.msn.com
http://www.uol.com.br
https://www.google.de
http://www.yandex.ru
http://www.hao123.com
https://www.google.co.uk
https://www.reddit.com
https://www.ebay.com
https://www.google.fr
https://www.t.co
http://www.tmall.com
http://www.google.com.br
https://www.360.cn
http://www.sohu.com
https://www.amazon.co.jp
http://www.pinterest.com
https://www.netflix.com
http://www.google.it
https://www.google.ru
https://www.microsoft.com
http://www.google.es
https://www.wordpress.com
http://www.gmw.cn
https://www.tumblr.com
http://www.paypal.com
http://www.blogspot.com
http://www.imgur.com
https://www.stackoverflow.com
https://www.aliexpress.com
https://www.naver.com
http://www.ok.ru
https://www.apple.com
http://www.github.com
http://www.chinadaily.com.cn
http://www.imdb.com
https://www.google.co.kr
http://www.fc2.com
http://www.jd.com
http://www.blogger.com
http://www.163.com
http://www.google.ca
https://www.whatsapp.com
https://www.amazon.in
http://www.office.com
http://www.google.co.id
http://www.youku.com
https://www.example.com
http://www.craigslist.org
https://www.amazon.de
http://www.nicovideo.jp
https://www.google.pl
http://www.soso.com
http://www.bilibili.com
http://www.dropbox.com
http://www.xinhuanet.com
http://www.outbrain.com
http://www.pixnet.net
http://www.alibaba.com
http://www.alipay.com
http://www.chrome.com
http://www.booking.com
http://www.googleusercontent.com
http://www.google.com.au
http://www.popads.net
http://www.cntv.cn
http://www.zhihu.com
https://www.amazon.co.uk
http://www.diply.com
http://www.coccoc.com
https://www.cnn.com
http://www.bbc.co.uk
https://www.twitch.tv
https://www.wikia.com
http://www.google.co.th
http://www.go.com
https://www.google.com.ph
http://www.doubleclick.net
http://www.onet.pl
http://www.googleadservices.com
http://www.accuweather.com
http://www.googleweblight.com
http://www.answers.yahoo.com"""


async def do_parallel(urls):
    async with aiohttp.ClientSession() as sess:
        ret = await asyncio.gather(*(get(url, sess) for url in urls))
    print("Finalized all. Return is a list of len {} outputs.".format(len(ret)))


@app.route('/try-parallel')
def try_parallel():
    urls = websites.split("\n")
    start = time.time()
    asyncio.run(do_parallel(urls))
    end = time.time()
    return "Took {} seconds to pull {} websites.".format(end - start, len(urls)), 200

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
    app.run(host='0.0.0.0', port=3000)

    # PROD
    # app.run()
