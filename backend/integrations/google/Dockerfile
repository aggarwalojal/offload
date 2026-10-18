# Build from repository root:
# docker build -f backend/integrations/google/Dockerfile -t timeslice-calendar .
FROM python:3.13-slim
WORKDIR /app
COPY backend/integrations/google/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/integrations/google /app/backend/integrations/google
COPY backend/schemas.py /app/backend/schemas.py
COPY backend/profile.py /app/backend/profile.py
RUN useradd --create-home timeslice
USER timeslice
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.integrations.google.public_app:create_public_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --no-access-log --no-proxy-headers"]
