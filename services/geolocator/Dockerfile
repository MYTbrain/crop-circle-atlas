FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CROP_CIRCLE_ATLAS_ROOT=/app \
    CROP_CIRCLE_GEO_CACHE=/cache \
    CROP_CIRCLE_GEO_API_HOST=0.0.0.0 \
    CROP_CIRCLE_GEO_API_PORT=8765 \
    CROP_CIRCLE_GEO_ALLOW_CONTAINER_BIND=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/geolocator /app/services/geolocator
RUN python -m pip install --no-cache-dir -e "/app/services/geolocator[server,stac]"
COPY data /app/data
COPY schemas /app/schemas

VOLUME ["/cache"]
EXPOSE 8765
CMD ["python", "-m", "crop_circle_geo.cli", "serve-api"]
