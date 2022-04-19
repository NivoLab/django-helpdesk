FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1
WORKDIR /app

ADD requirements.txt /app
# install requriements 
RUN python3.10 -m pip install --upgrade pip
RUN python3.10 -m pip install -r requirements.txt

ADD . /app

WORKDIR /app/demo

CMD python3.10 manage.py migrate && \
    python3.10 manage.py runserver 0.0.0.0:8000