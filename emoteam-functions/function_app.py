import azure.functions as func
import logging
from model import SpectroEdaMusicNet
import torch
import os
from azure.storage.blob import BlobServiceClient
from PIL import Image
import json
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import tempfile
from dotenv import load_dotenv
import requests
from azure.core.exceptions import ResourceExistsError
from azure.core.exceptions import ResourceNotFoundError

# from emoteam import app

load_dotenv()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
model = SpectroEdaMusicNet()
storage_connection_string = os.environ['STORAGE_CONNECTION_STRING']

@app.route(route="process_mp3", methods=['POST'])
def process_mp3(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
        if not req_body or not isinstance(req_body, list):
            return func.HttpResponse(
                "Request body is required and should be a list of dictionaries..",
                status_code=400
            )

        for song in req_body:
            print("song: ", song)
            if not isinstance(song, dict):
                logging.warning("Invalid song data found in the payload.")
                continue
            preview_url = song.get('preview_url')
            print("preview_url: ", preview_url)
            track_id = song.get('track_id').lower()
            print("track_id: ", track_id)


            # Download MP3 file from preview URL
            # Make the GET request to fetch the MP3 data
            response = requests.get(preview_url)

            # Check if the request was successful (status code 200)
            if response.status_code == 200:
                mp3_data = response.content
                print("MP3 data fetched successfully")
            else:
                print(f"Failed to fetch MP3 data. Status code: {response.status_code}")

            # Create Azure BlobServiceClient using connection string
            try:
                blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
                print("Blob service client created successfully")
            except Exception as e:
                print("Error creating Blob service client:", str(e))

            # Create container with track ID as name
            container_name = f'spotify-{track_id}'
            try:
            # Create the container with the specified name
                container_client = blob_service_client.create_container(container_name)
                print(f"Container '{container_name}' created successfully")
            except ResourceExistsError:
                print(f"Container '{container_name}' already exists")
            except Exception as e:
                print(f"Error occurred while creating container '{container_name}': {e}")

            # Upload MP3 file as blob
            try:
                # Upload the mp3 data as a blob with the specified name
                blob_client = container_client.upload_blob(name=f'song-{track_id}.mp3', data=mp3_data)
                print(f"Blob 'song-{track_id}.mp3' uploaded successfully")
            except ResourceNotFoundError:
                print("Container does not exist")
            except Exception as e:
                print(f"Error occurred while uploading blob: {e}")

        return func.HttpResponse("MP3 files uploaded successfully", status_code=200)
    except Exception as e:
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
    
@app.route(route="predict")
def predict(req: func.HttpRequest) -> func.HttpResponse:
    # scoped to a single song id, and for a single spotify user
    logging.info('predict function processed a request.')
    # get spotify song id
    song_id = req.params.get('id')
    user_id = req.params.get('userId')
    if not song_id:
        return func.HttpResponse(
            'Missing spotify song id query param',
            status_code=400
        )

    if not user_id:
        return func.HttpResponse(
            'Missing spotify user id query param',
            status_code=400
        )
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
    except Exception as e:
        logging.error(f'could not connect to blob storage with connection string, {e}')
        return func.HttpResponse('cannot connect to blob storage', status_code=500)

    # we need spectrogram, eda and music vector, get those from blob storage
    try:
        container_name = f'spotify-{song_id}'
        song_container = blob_service_client.get_container_client(container=container_name)
    except Exception as e:
        logging.error(f'could not get container for song {song_id}, {e}')
        return func.HttpResponse('Song container not found in blob storage', status_code=404)

    if not song_container.exists:
        func.HttpResponse(
            'Container for song id {song_id} does not exist',
            status_code=400
        )

    # list blobs in the container
    blobs = song_container.list_blobs()
    temp_files: dict[str, str] = {}
    for blob in blobs:
        logging.info(f'container {container_name} and blob {blob.name}')
        # blob.name is the full file name including the file extension
        name = blob.name.lower()
        if name.startswith('arousal') or name.startswith('valence'):
            # only download the user's EDA
            # expected format: {valence/arousal}-{song id}-{user id}.txt
            # example: valence-1-abcdefg.txt
            blob_user_id = name.split('.')[0].split('-')[-1]
            if blob_user_id != user_id:
                logging.info('found EDA not belonging to user ID, skipping...')
                continue

        blob_client = song_container.get_blob_client(blob=blob.name)
        path = os.path.join(tempfile.gettempdir(), name)
        with open(file=path, mode="wb") as new_file:
            stream = blob_client.download_blob()
            new_file.write(stream.readall())
        temp_files[name] = path

    # load respective data
    valence_eda: torch.Tensor = None
    arousal_eda: torch.Tensor = None
    for name, path in temp_files.items():
        is_arousal_eda = name.startswith('arousal')
        is_valence_eda = name.startswith('valence')
        if name.startswith('spectrogram'):
            # spectrogram
            spectrogram = Image.open(path)
            spectrogram = spectrogram.convert("L")  # Convert to grayscale
            spectrogram = np.array(spectrogram)
            spectrogram = torch.tensor(spectrogram, dtype=torch.float32).unsqueeze(0)
        elif name.startswith('features'):
            # opensmile features
            music_df = pd.read_csv(path, index_col='musicId')

            # TODO: after training, we need to know exactly which features are the best for feature selection
            # the music_df should NOT have extraneous features, at the preprocessing stage we should already
            # extract the relevant features
            # the csv file should also not have any target cols

            music_features = music_df.iloc[0]
            music_vector = torch.tensor(np.array(music_features))
        elif is_valence_eda or is_arousal_eda:
            with open(path, "r") as f:
                eda_signal = np.array(json.loads(f.read()))
            if len(eda_signal) != 896:
                x = np.arange(len(eda_signal))
                f = interp1d(x, eda_signal, kind='linear')
                x_new = np.linspace(0, len(eda_signal) - 1, 896)
                interpolated_signal = f(x_new)
            else:
                interpolated_signal = eda_signal

            tensor = torch.tensor(interpolated_signal, dtype=torch.float32)
            if is_arousal_eda:
                arousal_eda = tensor
            elif is_valence_eda:
                valence_eda = tensor

    # make sure required data are not null
    if spectrogram is None or music_vector is None or arousal_eda is None or valence_eda is None:
        return func.HttpResponse('missing data, cannot run predictions unless all are present', status_code=400)

    # logging data shapes
    logging.info(f'spectrogram shape: {spectrogram.size()}')
    logging.info(f'music vector shape: {music_vector.size()}')
    logging.info(f'arousal_eda shape: {arousal_eda.size()}')
    logging.info(f'valence_eda shape: {valence_eda.size()}')
    
    
    # try to load model and do preictions
    try:
        device = torch.device('cpu')
        model.to(device)
        model.load_state_dict(torch.load('best_model.pt', map_location='cpu'))
        model.eval()

        # TODO: predict and return predicted values
    except Exception as e:
        logging.error(f'torch could not load state dict, {e}')
        return func.HttpResponse('cannot load model', status_code=500)
    finally:
        # remove temp files no matter what
        for path in temp_files.values():
            if os.path.exists(path):
                os.remove(path)

    
    return func.HttpResponse('done', status_code=200)