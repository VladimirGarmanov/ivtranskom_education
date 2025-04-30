import logging
import time
import openai
import requests
from fastapi import FastAPI, Request
import json
import aiohttp
import configparser
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Инициализация файла конфигурации
config = configparser.ConfigParser()
config.read('config.ini')

# Получение настроек из config.ini
openai_api_key = config.get('Config', 'openai_api_key')
assistant_id = config.get('Config', 'assistant_id')
ACCESS_TOKEN = config.get('Config', 'whatsapp')

# Инициализация клиента OpenAI
client = openai.OpenAI(api_key=openai_api_key)
Assistant_ID = assistant_id

# Инициализация FastAPI-приложения
app = FastAPI()

# Глобальные словари и множества
price_sent = {}
chat_sessions = {}
initiated_users = set()

# Допустимые группы для обработки
groups = ['Консультант Ivtranskom']

# Адрес для отправки сообщений
API_URL = 'https://gate.whapi.cloud/messages/text'

async def send_email(subject, body, to_email, from_email, from_email_password):
    """
    Отправка электронного письма с помощью aiosmtplib.
    """
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    # Создание MIME-сообщения
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Подключение к SMTP-серверу, отправка письма
    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_server,
            port=smtp_port,
            start_tls=True,
            username=from_email,
            password=from_email_password
        )
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email. Error: {e}")

async def send_message(chat_id: str, text: str):
    """
    Отправка текстового сообщения через WhatsApp API.
    """
    if '@' not in chat_id:
        chat_id = f"{chat_id}@s.whatsapp.net"
    data = {
        "to": chat_id,
        "body": text,
        "typing_time": 0
    }
    headers = {
        'accept': 'application/json',
        'authorization': f'Bearer {ACCESS_TOKEN}',
        'content-type': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, data=json.dumps(data)) as response:
            if response.status == 200:
                print("Message sent successfully")
            else:
                print(f"Failed to send message: {response.status}")
                response_text = await response.text()
                print(f"Response: {response_text}")

async def add_user(chat_id):
    """
    Создаёт новую 'нитку' (thread) для пользователя (чат) и
    сохраняет её в глобальном словаре chat_sessions.
    """
    thread = client.beta.threads.create()
    chat_sessions[chat_id] = thread.id
    price_sent[chat_id] = False

async def handle_with_assistant(message, chat_id):
    """
    Основная логика взаимодействия с Assistant (OpenAI).
    Создаёт либо извлекает thread_id и вызывает чат-ран.
    """
    print('генерация началась')

    # Если нет thread для данного чата, создаём
    my_assistant_instructions = client.beta.assistants.retrieve(assistant_id).instructions
    print(my_assistant_instructions)
    response = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        input=f"{my_assistant_instructions} {message}"
    )
    fixed_content = response.output_text
    await send_message(chat_id, fixed_content)


@app.post("/webhook/ivtranskom")
async def webhook(request: Request):
    """
    Webhook-эндпоинт для обработки входящих сообщений из WhatsApp.
    Обрабатываются только сообщения из групп, указанных в списке 'groups'.
    """
    try:
        payload = await request.json()
        messages = payload.get("messages", [])

        for message in messages:
            sender_id = message.get("from")
            message_text = message.get("text", {}).get("body", "")
            chat_name = message.get('chat_name')
            chat_id = message.get('chat_id')
            me = message.get('from_me')
            print(f"Sender ID: {sender_id}")
            print(f"Message Text: {message_text}")
            print(me)
            print(chat_name)

            # Обрабатываем только сообщения из групп, перечисленных в 'groups'
            if chat_name and chat_name in groups:
                # Префикс "group" в тексте, чтобы ассистент понимал контекст
                message_text = f"group {message_text}"
                print(message_text)
                if str(me) == 'False':
                    await handle_with_assistant(message_text, chat_id)
            # Если chat_name не указан (это может быть приватный чат), игнорируем
            # или можно добавить свою логику обработки личных сообщений

        return {"status": "success", "data": payload}

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1000)
