FROM python:3.12-slim

WORKDIR /app

RUN pip install nicegui pydantic

COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
