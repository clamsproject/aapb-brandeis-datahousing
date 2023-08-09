FROM python:3-slim-buster

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
RUN pip install --upgrade pip
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY . /app/

CMD ["python3", "/app/app.py", "-s", "/mnt/llc/llc_data/clams", "-p", "5000", "-n"]
