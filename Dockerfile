FROM python:3.11-slim

WORKDIR /app

# Install build deps, compile python packages, lalu hapus build deps
# (mengurangi peak memory saat build & ukuran image akhir)
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libssl-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libssl-dev \
    && rm -rf /var/lib/apt/lists/* /root/.cache

COPY . .

CMD ["python", "main.py"]
