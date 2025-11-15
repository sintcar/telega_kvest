FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё приложение
COPY . .

# По умолчанию просто ждем указания, какой процесс запускать
CMD ["python", "run_bot.py"]
