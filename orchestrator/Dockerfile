FROM python:3.9-slim

RUN apt update
RUN apt install python3 -y

# Install Docker CLI
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*
RUN pip install docker requests

WORKDIR /app

COPY . /app

# Run the script
CMD ["python", "-u", "orchestrator-service.py"]