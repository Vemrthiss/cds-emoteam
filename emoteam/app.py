import streamlit as st
import requests
import datetime
import calendar
from dotenv import load_dotenv
import os
import numpy as np
import pandas as pd
import plotly.express as px

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
eda_sample_data = np.loadtxt('eda.txt')
timestamps = np.arange(len(eda_sample_data)) * 0.02
df = pd.DataFrame({
    'Time (s)': timestamps,
    'EDA': eda_sample_data
})
fig = px.line(df, x='Time (s)', y='EDA', title='Sample Electrodermal Activity Over Time',
              labels={'EDA': 'Electrodermal Activity (μS)'})
fig.update_traces(mode='lines+markers')
st.plotly_chart(fig)

st.header("Do predictions here!")
proc_req = st.button('Get songs')
if proc_req:
    headers = {'Authorization': f'Bearer {access_token}'}
    timestamp = calendar.timegm(after_date.timetuple())  # seconds
    body = {'limit': limit, 'after': timestamp * 1000}
    with st.spinner('Processing songs...'):
        processed_tracks = requests.post(f'{api_url}/get-recent', headers=headers, json=body).json()
    with st.spinner('Running predictions...'):
        predict_body = list(map(lambda track: track['track_id'], processed_tracks))
        prediction_response = requests.post(f'{api_url}/predict', headers=headers, json=predict_body).json()

    predictions_df = pd.DataFrame(prediction_response)
    predictions_df.set_index('track_id', inplace=True)
    processed_tracks_df = pd.DataFrame(processed_tracks)
    processed_tracks_df.set_index('track_id', inplace=True)
    predictions_df = predictions_df.merge(processed_tracks_df, left_index=True, right_index=True)
    predictions_df.reset_index(inplace=True)
    fig = px.scatter(predictions_df,
                     x='valence',
                     y='arousal',
                     color='track_id',
                     color_discrete_sequence=px.colors.qualitative.Plotly,
                     title='Valence vs. Arousal Predictions',
                     range_x=[-1, 1], range_y=[-1, 1],
                     hover_data=['track_id', 'track_name'],
                     labels={
                         "valence": "Valence (-1 to 1)",
                         "arousal": "Arousal (-1 to 1)"
                     })
    fig.update_layout(
        shapes=[
            # Line Vertical
            {
                'type': 'line',
                'x0': 0,
                'y0': -1,
                'x1': 0,
                'y1': 1,
                'line': {
                    'color': 'Black',
                    'width': 2,
                    'dash': 'dash',
                },
            },
            # Line Horizontal
            {
                'type': 'line',
                'x0': -1,
                'y0': 0,
                'x1': 1,
                'y1': 0,
                'line': {
                    'color': 'Black',
                    'width': 2,
                    'dash': 'dash',
                },
            }
        ],
        xaxis=dict(range=[-1, 1], zeroline=False),
        yaxis=dict(range=[-1, 1], zeroline=False)
    )
    fig.update_traces(marker=dict(size=10))
    st.plotly_chart(fig)
