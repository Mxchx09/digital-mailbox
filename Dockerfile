FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/postfach.db

# Eigener Benutzer ohne Rechte; /data ist der einzige beschreibbare Ort (Datenbank)
RUN useradd --system --uid 10001 --no-create-home postfach \
 && mkdir /data && chown postfach /data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static static
COPY templates templates

USER postfach
EXPOSE 8000
VOLUME /data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"

# Ein Prozess mit Threads: gemeinsame Zaehler (Login-Sperre, Limit). Keine Zugriffslogs, damit keine IPs entstehen.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8000", \
     "--access-logfile", "/dev/null", "--error-logfile", "-", "--no-control-socket", "app:app"]
