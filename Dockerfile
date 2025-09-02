FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install uv
RUN uv pip install --system -r requirements.txt

COPY . .

CMD ["python", "main.py"]