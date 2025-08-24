# Twitch Ollama Chatbot - Docker Configuration
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r chatbot && useradd -r -g chatbot chatbot

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY chatbot/ ./chatbot/
COPY blocked_words.txt .
COPY setup.py .

# Install the package
RUN pip install -e .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs && \
    chown -R chatbot:chatbot /app

# Switch to non-root user
USER chatbot

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=/app/data/chatbot.db
ENV LOG_FILE=/app/logs/chatbot.log

# Expose health check port (if implemented)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; import aiohttp; asyncio.run(aiohttp.ClientSession().get('http://localhost:8080/health').close())" || exit 1

# Run the application
CMD ["python", "-m", "chatbot.main"]