FROM python:3.10

WORKDIR /app
COPY . .

RUN pip install --upgrade pip && pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "gartic_project.asgi:application"]