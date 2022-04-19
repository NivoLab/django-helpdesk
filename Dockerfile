FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1
WORKDIR /app

# install requriements 
ADD requirements.txt /app
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ADD . /app

WORKDIR demo/demodesk

CMD python3.10 manage.py migrate && \
    python3.10 manage.py runserver 0.0.0.0:8000