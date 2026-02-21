FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["python", "main.py"]

LABEL org.opencontainers.image.source=https://github.com/watermellon2018/telegram_expense_bot
LABEL org.opencontainers.image.description="Telegram бот для учёта расходов"
LABEL org.opencontainers.image.version="3.0"
LABEL org.opencontainers.image.authors="watermellon2018"