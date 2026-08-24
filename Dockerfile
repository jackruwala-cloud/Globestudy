# API service container for the International Student Advisor "brain".
# Build context = this directory (intl-student-advisor/).
FROM python:3.11-slim

WORKDIR /app

# Install runtime deps first (better layer caching).
COPY api/requirements-api.txt /app/api/requirements-api.txt
RUN pip install --no-cache-dir -r /app/api/requirements-api.txt

# App code.
COPY . /app

# Build the retrievable knowledge base into data/chunks.json at image build time.
RUN python -m ingestion.build_index

# Cloud hosts inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} expands.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
