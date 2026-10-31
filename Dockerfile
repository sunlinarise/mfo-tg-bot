# Python 3.11 is required: aiogram needs Python >= 3.10.
# Persistent data (if added later) belongs in /app/data.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
 && (pip install --no-cache-dir --retries 5 -r requirements.txt \
     || pip install --no-cache-dir --retries 5 \
        -i https://pypi.org/simple -r requirements.txt)

COPY . .

RUN mkdir -p /app/data

CMD ["python", "main.py"]
