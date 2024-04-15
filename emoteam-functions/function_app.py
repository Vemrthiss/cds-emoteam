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
import requests
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import ContainerClient
from spectrogram import make_spectrogram
from wav import mp3_to_wav
from music_features import wav_to_features
import threading

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
model = SpectroEdaMusicNet()
storage_connection_string = os.environ['STORAGE_CONNECTION_STRING']
lock = threading.Lock()

@app.route(route="process_mp3", methods=['POST'])
def process_mp3(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('process_mp3 function processed a request.')

    tempfiles = [] # array of tempfile paths
    try:
        req_body = req.get_json()
        if not req_body:
            return func.HttpResponse(
                "Request body is required and should be a list of dictionaries..",
                status_code=400
            )
        song = req_body
        preview_url = song.get('preview_url')
        track_id = song.get('track_id').lower()
        if not isinstance(song, dict) or preview_url is None or track_id is None:
            return func.HttpResponse(
                "Invalid or missing song data found in the payload.",
                status_code=400
            )

        # Download MP3 file from preview URL
        # Make the GET request to fetch the MP3 data
        response = requests.get(preview_url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            mp3_data = response.content
        else:
            logging.warning("Failed to fetch MP3 data. Status code")

        # Create Azure BlobServiceClient using connection string
        try:
            blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        except Exception as e:
            logging.error("Error creating Blob service client:", str(e))

        # Create container with track ID as name
        container_name = f'spotify-{track_id}'
        container_client: ContainerClient = None
        try:
            # Create the container with the specified name
            container_client = blob_service_client.create_container(container_name)
        except ResourceExistsError:
            container_client = blob_service_client.get_container_client(container=container_name)
            logging.info("Container '%s' already exists" % container_name)
        except Exception as e:
            logging.error("Error occurred while creating container '%s'" % container_name, e)

        # DO PREPROCESSING HERE
        upload_status = {
            'track_id': track_id, # LOWER-CASE(D)
            'mp3': False,
            'spectrogram': False,
            'wav': False,
            'features': False
        }
        # 1) upload mp3
        mp3_file_name = f'song-{track_id}.mp3'
        try:
            # Upload the mp3 data as a blob with the specified name
            container_client.upload_blob(name=mp3_file_name, data=mp3_data)
            logging.info("Blob '%s' uploaded successfully" % mp3_file_name)
            upload_status['mp3'] = True
        except ResourceNotFoundError as e:
            logging.error("Container does not exist %s" % e)
        except ResourceExistsError:
            logging.info("mp3 resource already exists for track %s" % track_id)
            upload_status['mp3'] = True
        except Exception as e:
            logging.warning("Error occurred while uploading mp3 blob: %s" % e)

        # create temp mp3 file
        mp3_path = os.path.join(tempfile.gettempdir(), mp3_file_name)
        with open(file=mp3_path, mode="wb") as new_file:
            new_file.write(mp3_data)
        tempfiles.append(mp3_path)

        # assume container does not exist is caught above, do not catch anymore
        # 2) wav
        try:
            wav_file_name = f'wav-{track_id}.wav'
            wav_path = os.path.join(tempfile.gettempdir(), wav_file_name)
            mp3_to_wav(mp3_path, wav_path)
            with open(wav_path, 'rb') as wav_file:
                wav_bytes = wav_file.read()
            container_client.upload_blob(name=wav_file_name, data=wav_bytes)
            logging.info("Blob '%s' uploaded successfully" % wav_file_name)
            upload_status['wav'] = True
        except ResourceExistsError:
            logging.info("wav resource already exists for track %s" % track_id)
            upload_status['wav'] = True
        except Exception as e:
            logging.warning('Error occurred while uploading wav blob: %s' % e)

        # 3) music features
        try:
            features_file_name = f'features-{track_id}.csv'
            features_path = os.path.join(tempfile.gettempdir(), features_file_name)
            wav_to_features(wav_path, features_path, track_id)
            with open(features_path, 'rb') as features_file:
                features_bytes = features_file.read()
            container_client.upload_blob(name=features_file_name, data=features_bytes)
            logging.info("Blob '%s' uploaded successfully" % features_file_name)
            upload_status['features'] = True
        except ResourceExistsError:
            logging.info("features resource already exists for track %s" % track_id)
            upload_status['features'] = True
        except Exception as e:
            logging.warning('Error occurred while uploading features csv: %s' % e)

        # 4) spectrogram
        try:
            spectrogram_file_name = f'spectrogram-{track_id}.png'
            spectrogram_path = os.path.join(tempfile.gettempdir(), spectrogram_file_name)
            with lock:
                make_spectrogram(mp3_path, spectrogram_path)
            with open(spectrogram_path, 'rb') as spectrogram_file:
                spectrogram_bytes = spectrogram_file.read()
            container_client.upload_blob(name=spectrogram_file_name, data=spectrogram_bytes)
            logging.info("Blob '%s' uploaded successfully" % spectrogram_file_name)
            upload_status['spectrogram'] = True
        except ResourceExistsError:
            logging.info("spectrogram resource already exists for track %s" % track_id)
            upload_status['spectrogram'] = True
        except Exception as e:
            logging.warning("Error occurred while uploading spectrogram blob: %s" % e)
        

        return func.HttpResponse(json.dumps(upload_status), status_code=200)
    except Exception as e:
        return func.HttpResponse("Error: %s" % e, status_code=500)
    finally:
        # always clear tempfiles
        for tempfile_path in tempfiles:
            if os.path.exists(tempfile_path):
                os.remove(tempfile_path)

 
@app.route(route="predict", methods=['POST'])
def predict(req: func.HttpRequest) -> func.HttpResponse:
    # scoped to a single song id, and for a single spotify user
    logging.info('predict function processed a request.')
    req_body = req.get_json()
    if not req_body:
        return func.HttpResponse("Request body is required", status_code=400)
    # get spotify song/track id
    TRACK_ID = req_body.get('track_id')
    track_id = TRACK_ID.lower()
    user_id = req_body.get('user_id')
    if not track_id:
        return func.HttpResponse(
            'Missing spotify track id param',
            status_code=400
        )

    if not user_id:
        return func.HttpResponse(
            'Missing spotify user id param',
            status_code=400
        )
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
    except Exception as e:
        logging.error('could not connect to blob storage with connection string %s' % e)
        return func.HttpResponse('cannot connect to blob storage', status_code=500)

    # we need spectrogram, eda and music vector, get those from blob storage
    try:
        container_name = f'spotify-{track_id}'
        song_container = blob_service_client.get_container_client(container=container_name)
    except Exception as e:
        logging.error('could not get container for song %s with error %s' % (track_id, e))
        return func.HttpResponse('Song container not found in blob storage', status_code=404)

    if not song_container.exists:
        return func.HttpResponse(
            'Container for song id {track_id} does not exist',
            status_code=400
        )

    # list blobs in the container
    blobs = song_container.list_blobs()
    temp_files: dict[str, str] = {}
    for blob in blobs:
        logging.info('container %s and blob %s' % (container_name, blob.name))
        # blob.name is the full file name including the file extension
        name = blob.name.lower()
        # TODO: uncomment this part until we support user-level eda
        # if name.startswith('arousal') or name.startswith('valence'):
        #     # only download the user's EDA
        #     # expected format: {valence/arousal}-{song id}-{user id}.txt
        #     # example: valence-1-abcdefg.txt
        #     blob_user_id = name.split('.')[0].split('-')[-1]
        #     if blob_user_id != user_id:
        #         logging.info('found EDA not belonging to user ID, skipping...')
        #         continue

        blob_client = song_container.get_blob_client(blob=blob.name)
        path = os.path.join(tempfile.gettempdir(), name)
        with open(file=path, mode="wb") as new_file:
            stream = blob_client.download_blob()
            new_file.write(stream.readall())
        temp_files[name] = path

    # get sample EDAs
    eda_container = blob_service_client.get_container_client(container='eda-data')
    if not eda_container.exists:
        return func.HttpResponse('eda container does not exist', status_code=500)
    blobs = eda_container.list_blobs()
    for blob in blobs:
        logging.info('getting eda with blob %s' % blob.name)
        # blob.name is the full file name including the file extension
        name = blob.name.lower()
        blob_client = eda_container.get_blob_client(blob=blob.name)
        path = os.path.join(tempfile.gettempdir(), name)
        with open(file=path, mode="wb") as new_file:
            stream = blob_client.download_blob()
            new_file.write(stream.readall())
        temp_files[name] = path


    # load respective data
    eda_tensor: torch.Tensor = None
    for name, path in temp_files.items():
        if name.startswith('spectrogram'):
            # spectrogram
            spectrogram = Image.open(path)
            spectrogram = spectrogram.convert("L")  # Convert to grayscale
            spectrogram = np.array(spectrogram)
            spectrogram = torch.tensor(spectrogram, dtype=torch.float32).unsqueeze(0)
        elif name.startswith('features'):
            # opensmile features
            music_df = pd.read_csv(path)
            music_features = music_df.iloc[0]
            music_vector = torch.tensor(np.array(music_features), dtype=torch.float32)
        elif name.startswith('arousal'):
            # blob is arousal.txt in azure storage, default to arousal which is in line with our training methods
            with open(path, "r") as f:
                eda_signal = np.array(json.loads(f.read()))
            if len(eda_signal) != 896:
                x = np.arange(len(eda_signal))
                f = interp1d(x, eda_signal, kind='linear')
                x_new = np.linspace(0, len(eda_signal) - 1, 896)
                interpolated_signal = f(x_new)
            else:
                interpolated_signal = eda_signal

            eda_tensor = torch.tensor(interpolated_signal, dtype=torch.float32)

    # make sure required data are not null
    if spectrogram is None or music_vector is None or eda_tensor is None:
        return func.HttpResponse('missing data, cannot run predictions unless all are present', status_code=400)

    spectrogram = spectrogram.unsqueeze(0) # add batch dimension
    eda_tensor = eda_tensor.unsqueeze(0).unsqueeze(0) # add batch dimension and 2nd dimension "1", becomes 1,1,896
    #TODO: does LSTM make sense for STATIC features?
    music_vector = music_vector.unsqueeze(0) # add batch dimension
    # logging data shapes
    spectrogram_shape = str(spectrogram.size())
    music_vector_shape = str(music_vector.size())
    eda_shape = str(eda_tensor.size())
    logging.info('spectrogram shape: %s' % spectrogram_shape)
    logging.info('music vector shape: %s' % music_vector_shape)
    logging.info('eda shape: %s' % eda_shape)
    
    # try to load model and do predictions
    try:
        device = torch.device('cpu')
        model.to(device)
        model.load_state_dict(torch.load('best_model.pt', map_location='cpu'))
        model.eval()

        # predict
        pred_arousal, pred_valence = model(spectrogram, eda_tensor, music_vector)
        pred_arousal = pred_arousal.item()
        pred_valence = pred_valence.item()
        return func.HttpResponse(json.dumps({
            'track_id': TRACK_ID,
            'arousal': pred_arousal,
            'valence': pred_valence
        }), status_code=200)
    except Exception as e:
        logging.error('ran into problems during prediction %s' % e)
        return func.HttpResponse('cannot load model', status_code=500)
    finally:
        # remove temp files no matter what
        for path in temp_files.values():
            if os.path.exists(path):
                os.remove(path)