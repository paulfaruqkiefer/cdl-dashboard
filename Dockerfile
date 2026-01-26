# Use Python 3.11 slim
FROM python:3.11-slim

# Set working directory to root
WORKDIR /

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app and data
COPY app ./app
COPY data ./data

# Expose port for Fly.io
EXPOSE 8080

# Start gunicorn with a longer timeout
CMD ["gunicorn", "app.app:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]
