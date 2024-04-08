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

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
model = SpectroEdaMusicNet()
storage_connection_string = os.environ['STORAGE_CONNECTION_STRING']

@app.route(route="process_mp3")
def process_mp3(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )
    
@app.route(route="predict")
def predict(req: func.HttpRequest) -> func.HttpResponse:
    # scoped to a single song id
    logging.info('predict function processed a request.')
    # get spotify song id
    song_id = req.params.get('id')
    if not song_id:
        return func.HttpResponse(
            'Missing spotify song id query param',
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
        blob_client = song_container.get_blob_client(blob=blob.name)
        path = os.path.join(tempfile.gettempdir(), blob.name)
        with open(file=path, mode="wb") as new_file:
            stream = blob_client.download_blob()
            new_file.write(stream.readall())
        temp_files[blob.name] = path

    # load respective data
    valence_eda: torch.Tensor = None
    arousal_eda: torch.Tensor = None
    for file_name, path in temp_files.items():
        name = file_name.lower()
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

    