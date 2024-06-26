# The Emoteam

Team members:

- Joseph Low, 1005013
- Abram Tan, 1005057
- Joel Tay, 1005117
- Su Chang, 1004893
- Ankita Sushil Parashar, 1005478

Final group project code repository for **50.038 Computational Data Science Spring 2024**

This repository is for the **application part** of our project. The repository that contains code pertaining to model training is found [here](https://github.com/jolow99/multi_modal_cnn)

## Architecture

We have three separate apps:

1. `emoteam`: Streamlit-powered dashboard for the user
2. `emoteam-auth`: Flask app, serving as an "API gateway" for authentication, handling requests to spotify, and in the future handling our ML models
3. `emoteam-functions`: Azure functions app, containing two functions to preprocess data and run predictions separately. It is deployed as a [containerized](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deploy-container?tabs=acr,bash,azure-cli&pivots=programming-language-python#configure-your-local-environment) function app.

The first two apps are deployed as **separate Azure app services**.

### Cold starts

Do note that both app services have a cold start procedure to them.

## Setup for development

Make sure you obtain the necessary `.env` files from @Vemrthiss, and place them in their respective _project_ roots (not repository root).

In particular, you should have `/emoteam/.env` and `emoteam-auth/.env` files

### emoteam-auth

Firstly, make sure you run the dev version of `app.run()`

```python
# TODO: make sure the correct app.run is used
if __name__ == '__main__':
    # DEV
    app.run(host='0.0.0.0', port=3000)

    # PROD
    # app.run()
```

Make sure that the right values for development are reflected in the `.env` file as well.

Run the following commands, making sure to create a virtual environment, activate it, and install required dependencies. The following will work for UNIX based machines, if you are using windows, please make the necessary changes (e.g. activating virtual environments).

```console
$ cd emoteam-auth
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
$ python app.py
```

### emoteam

You do not have to change any code, just make sure that the right values for development are reflected in the `.env` file as well.

Run the following commands, making sure to create a virtual environment, activate it, and install required dependencies. The following will work for UNIX based machines, if you are using windows, please make the necessary changes (e.g. activating virtual environments).

```console
$ cd emoteam
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
$ streamlit run app.py
```

## Deployment

### emoteam-functions

Make sure you have the following:

- Docker installed on your machine
- Azure CLI and logged in to Azure

```console
$ cd emoteam-functions
$ az login acr --name emoteam
$ docker build -t emoteam.azurecr.io/emoteam-functions .
$ docker push emoteam.azurecr.io/emoteam-functions
```

The azure functions project is setup for continuous deployment whenever a new image is pushed to the Azure Container Registry `emoteam`, under the repository `emoteam-functions`

> This is why we are pushing to `emoteam.azurecr.io/emoteam-functions`
