# To enable ssh & remote debugging on app service change the base image to the one below
# FROM mcr.microsoft.com/azure-functions/python:4-python3.11-appservice
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

COPY requirements.txt /
RUN pip install -r /requirements.txt

# Install FFMPEG
RUN apt-get update && \
    apt-get install -y ffmpeg

# install opensmile
RUN apt-get install -y cmake && \
    apt-get install -y build-essential
RUN wget https://github.com/audeering/opensmile/archive/refs/tags/v3.0.2.tar.gz
RUN tar xf v3.0.2.tar.gz -C /opt
RUN cd /opt/opensmile-3.0.2/ && ./build.sh
RUN mv /opt/opensmile-3.0.2/ /usr/local/bin/
RUN mv /usr/local/bin/opensmile-3.0.2/ /usr/local/bin/opensmile/
RUN chmod +rwx /usr/local/bin/opensmile/*

COPY . /home/site/wwwroot