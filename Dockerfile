# Use Python 3.11 slim
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app ./app

# Copy data folder
COPY data ./data

# Expose port
EXPOSE 8080

# Start the app with a longer timeout (helps large datasets)
CMD ["gunicorn", "app.app:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]
