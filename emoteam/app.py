import streamlit as st
import requests
import datetime
import calendar
from dotenv import load_dotenv
import os

load_dotenv()
api_url = os.environ.get('API_URL')

st.title("Emoteam")

if 'access_token' not in st.session_state:
    st.session_state.access_token = None


def validate_token(token):
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{api_url}/check-token', headers=headers)
    return response.json()


def check_login():
    params = st.query_params
    if params.get('code') is not None:
        # redirected from callback
        st.session_state.access_token = params.get('code')
        st.query_params.clear()

    if st.session_state.access_token is not None:
        resp = validate_token(st.session_state.access_token)
        if resp.get('valid'):
            return st.session_state.access_token
        else:
            # lazily, log in again, instead of refreshing
            st.write(f"""<meta http-equiv="refresh" content="0; url='{api_url}'">""", unsafe_allow_html=True)
            st.stop()
    else:
        st.write(f"""<meta http-equiv="refresh" content="0; url='{api_url}'">""", unsafe_allow_html=True)
        st.stop()


def get_preview_url(item):
    track = item['track']
    if track is not None:
        return track['preview_url']
    return None


access_token = check_login()
limit = st.slider("Maximum number of songs:", 1, 50, 20, 1)
today = datetime.datetime.now()
after_date = st.date_input(
    "Retrieve songs from:",
    max_value=today,
    value=today - datetime.timedelta(days=7),
    format='DD/MM/YYYY'
)
proc_req = st.button('Get songs')
if proc_req:
    headers = {'Authorization': f'Bearer {access_token}'}
    timestamp = calendar.timegm(after_date.timetuple())  # seconds
    body = {'limit': limit, 'after': timestamp * 1000}
    with st.spinner('Processing songs...'):
        songs = requests.post(f'{api_url}/get-recent', headers=headers, json=body).json()
    st.write(songs)
    tracks = list(map(get_preview_url, songs['items']))
    tracks = list(filter(lambda url: url is not None, tracks))
    st.write(tracks)
