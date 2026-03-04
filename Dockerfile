FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ bot/

# Run as non-root
RUN useradd --create-home appuser
USER appuser

CMD ["python", "-m", "bot.main"]
