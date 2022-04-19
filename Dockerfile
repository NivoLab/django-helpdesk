FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1

# install requriements 
RUN python3.10 -m pip install --upgrade pip
RUN python3.10 -m pip install -r requirements.txt

WORKDIR demo/demodesk

CMD python3.10 manage.py migrate && \
    python3.10 manage.py runserver 0.0.0.0:8000