FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (Scapy needs libpcap, psutil needs build-essential)
RUN apt-get update && apt-get install -y \
    gcc \
    iputils-ping \
    libpcap-dev \
    speedtest-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]
