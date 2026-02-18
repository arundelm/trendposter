FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY trendposter/ trendposter/

# Install with all optional deps
RUN pip install --no-cache-dir -e ".[all]"

# Create data directory
RUN mkdir -p /app/data

# Non-root user
RUN useradd -m trendposter
USER trendposter

CMD ["trendposter"]
