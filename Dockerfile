FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install uv
RUN uv pip install --system -r requirements.txt

COPY . .

# Default to test mode, can be overridden with RUN_MODE env var
ENV RUN_MODE=test

# Expose port for web server
EXPOSE 8000

CMD ["python", "main.py"]