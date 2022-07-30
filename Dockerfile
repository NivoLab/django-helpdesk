FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1
WORKDIR /app

ADD requirements.txt /app
# install requriements 
RUN python3.10 -m pip install --upgrade pip
RUN python3.10 -m pip install -r requirements.txt

ADD . /app

WORKDIR /app/demo

ENV DATABASE_HOST=45.82.139.99 \
    DATABASE_USER=nivohelpuser \
    DATABASE_NAME=nivo_help \
    DATABASE_PASS=123#n!rv4n4

CMD printenv >> /etc/environment && \
    python3.10 manage.py migrate && \
    python manage.py collectstatic --noinput && \
    gunicorn --bind 0.0.0.0:8000 demodesk.config.wsgi
