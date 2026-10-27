FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
#создаем рабочую директорию внутри контейнера
WORKDIR /bot

#копируем файлы с зависимостями
COPY requirements.txt .
#устанавливаем без кэша pip
RUN pip install --no-cache-dir -r requirements.txt

#копируем оставшийся код в контейнер
COPY . .
CMD ["python","main.py"]
