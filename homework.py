import logging.config
import os
import requests
import telebot
import time
import traceback

from dotenv import load_dotenv
from exceptions import HomeworkException
from logging import Handler, LogRecord
from http import HTTPStatus
from telegram import Bot, error


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
TIME_SLEEP = 30
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


# кастомный хендлер
class TelegramBotHandler(Handler):
    """Отправляет сообщение об ошибке в телеграм."""
    def __init__(self, token: str, chat_id: str):
        super().__init__()
        self.token = token
        self.chat_id = chat_id

    def emit(self, record: LogRecord):
        bot = telebot.TeleBot(self.token)
        bot.send_message(self.chat_id, self.format(record))

    def __str__(self) -> str:
        return 'Handler for sending logs to telegram'


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default_formatter': {
            'format': '%(asctime)s %(levelname)s %(message)s'
        },
    },
    'handlers': {
        'file_handler': {
            'class': 'logging.FileHandler',
            'formatter': 'default_formatter',
            'filename': 'main.log'
        },
        'telegram_handler': {
            'class': '__main__.TelegramBotHandler',
            'token': TELEGRAM_TOKEN,
            'chat_id': TELEGRAM_CHAT_ID,
            'formatter': 'default_formatter'
        },
    },
    'loggers': {
        'my_logger': {
            'handlers': ['file_handler'],
            'level': 'INFO',
            'propagate': True
        },
        'my_telegram_logger': {
            'handlers': ['file_handler', 'telegram_handler'],
            'level': 'ERROR',
            'propagate': True
        }
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
logger1 = logging.getLogger('my_logger')
logger2 = logging.getLogger('my_telegram_logger')


# кастомный декоратор
def sleep_error(timeout, retry=3):
    """Повторяет действие с паузой в 30сек в случае ошибки."""
    def time_sleep_error(function):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < retry:
                try:
                    value = function(*args, **kwargs)
                    if value is None:
                        return
                except Exception:
                    time.sleep(timeout)
                    retries += 1
        return wrapper
    return time_sleep_error


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger1.info('The message has been sent')
    except error.TelegramError:
        logger2.error('TELEGRAM_CHAT_ID is not available')
    except Exception:
        logger2.error(
            'Error sending the message',
            traceback.format_exc()
        )


def get_api_answer(current_timestamp):
    """Запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
        logger1.info('API request sent')
        if homework_statuses.status_code != HTTPStatus.OK:
            text_error = (
                f'The API returned the code {homework_statuses.status_code}'
            )
            logger2.error(text_error)
            raise HomeworkException(text_error)
    except ConnectionError:
        logger2.error('The endpoint is unavailable')
    except Exception:
        logger2.error(
            'Failure when requesting an endpoint',
            traceback.format_exc()
        )
    response = homework_statuses.json()
    logger1.info('API response received')
    return response


def check_response(response):
    """Проверка ответа API на корректность и выдача списка домашек."""
    logger1.info('Checking the correctness of the API response')
    if response.get('homeworks') is None:
        error_text = 'Dictionary key not found'
        logger2.error(error_text)
        raise HomeworkException(error_text)
    if isinstance(response['homeworks'], list) is False:
        error_message = 'The API response is not a list'
        logger2.error(error_message)
        raise HomeworkException(error_message)
    logger1.info('The API response is correct. Received a list of homework')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашки и возвращает строчку для отправки."""
    logger1.info('Determining the status of homework')
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError:
        message_error = 'Key not found'
        logger2.error(message_error)
        raise HomeworkException(message_error)
    else:
        if homework_status in HOMEWORK_VERDICTS:
            verdict = HOMEWORK_VERDICTS[homework_status]
            logger1.info('Received the text for the message')
            return (
                f'Изменился статус проверки работы "{homework_name}". '
                f'{verdict}'
            )
        message_text = 'Unknown homework status'
        logger2.error(message_text)
        raise HomeworkException(message_text)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    logger1.info('Checking the availability of environment variables')
    if PRACTICUM_TOKEN is None:
        logger2.critical(
            'Required environment variable is missing: PRACTICUM_TOKEN'
        )
        return False
    if TELEGRAM_TOKEN is None:
        logger2.critical(
            'Required environment variable is missing: TELEGRAM_TOKEN'
        )
        return False
    if TELEGRAM_CHAT_ID is None:
        logger2.critical(
            'Required environment variable is missing: TELEGRAM_CHAT_ID'
        )
        return False
    logger1.info('Environment variables are available')
    return True


@sleep_error(TIME_SLEEP)
def main():
    """Основная логика работы бота."""
    logger1.info('Start Bot')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())-30*24*60*60
    try:
        response = get_api_answer(current_timestamp)
        homeworks = check_response(response)
        if len(homeworks) > 0:
            send_message(bot, parse_status(homeworks[0]))
        else:
            logger2.error('The homework list is empty')
        current_timestamp = response['current_date']
    except IndexError:
        error_text = 'List index out of range'
        logger2.error(error_text)
        raise HomeworkException(error_text)
    except Exception as error:
        message = f'Program malfunction: {error}'
        logger2.error(message, traceback.format_exc())
        raise HomeworkException(message)
    else:
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
