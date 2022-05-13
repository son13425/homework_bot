import logging
import os
import requests
import time

from dotenv import load_dotenv
from exceptions import HomeworkException
from http import HTTPStatus
from telegram import Bot, error


logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    filename='main.log',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

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
        logger.info('The message has been sent')
    except error.TelegramError:
        message_telegram_error = 'TELEGRAM_CHAT_ID is not available'
        logger.error(message_telegram_error)
    except Exception:
        message_exception_error = 'Error sending the message'
        logger.error(message_exception_error)


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
        logger.info('API request sent')
        if homework_statuses.status_code != HTTPStatus.OK:
            text_error = (
                f'The API returned the code {homework_statuses.status_code}'
            )
            logger.error(text_error)
            raise HomeworkException(text_error)
    except ConnectionError:
        message_connection_error = 'The endpoint is unavailable'
        logger.error(message_connection_error)
    except Exception:
        message_exception_error = 'Failure when requesting an endpoint'
        logger.error(message_exception_error)
        raise HomeworkException(message_exception_error)
    response = homework_statuses.json()
    logger.info('API response received')
    return response


def check_response(response):
    """Проверка ответа API на корректность и выдача списка домашек."""
    logger.info('Checking the correctness of the API response')
    try:
        response['homeworks']
    except KeyError:
        message_error = 'Key not found'
        logger.error(message_error)
        raise HomeworkException(message_error)
    if isinstance(response['homeworks'], list) is False:
        error_message = 'The API response is not a list'
        logger.error(error_message)
        raise HomeworkException(error_message)
    logger.info('The API response is correct. Received a list of homework')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашки и возвращает строчку для отправки."""
    logger.info('Determining the status of homework')
    homework_name = homework.get('homework_name')
    if homework_name is None:
        homework_name_error = 'Key "homework_name" not found'
        logger.error(homework_name_error)
        raise KeyError(homework_name_error)
    homework_status = homework.get('status')
    if homework_name is None:
        homework_status_error = 'Key "status" not found'
        logger.error(homework_status_error)
        raise KeyError(homework_status_error)
    if homework_status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[homework_status]
        logger.info('Received the text for the message')
        return (
            f'Изменился статус проверки работы "{homework_name}". '
            f'{verdict}'
        )
    message_text = 'Unknown homework status!'
    logger.error(message_text)
    raise HomeworkException(message_text)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    logger.info('Checking the availability of environment variables')
    if PRACTICUM_TOKEN is None:
        logger.critical(
            'Required environment variable is missing: PRACTICUM_TOKEN'
        )
        return False
    if TELEGRAM_TOKEN is None:
        logger.critical(
            'Required environment variable is missing: TELEGRAM_TOKEN'
        )
        return False
    if TELEGRAM_CHAT_ID is None:
        logger.critical(
            'Required environment variable is missing: TELEGRAM_CHAT_ID'
        )
        return False
    logger.info('Environment variables are available')
    return True


@sleep_error(TIME_SLEEP)
def main():
    """Основная логика работы бота."""
    logger.info('Start Bot')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    previous_error = ""
    previous_message = ""
    try:
        response = get_api_answer(current_timestamp)
        homeworks = check_response(response)
        if len(homeworks) > 0:
            send_message(bot, parse_status(homeworks[0]))
        else:
            text_error = 'The homework list is empty'
            logger.error(text_error)
            if text_error != previous_message:
                send_message(bot, text_error)
                previous_message = text_error
        current_timestamp = response['current_date']
        time.sleep(RETRY_TIME)
    except IndexError:
        error_text = 'List index out of range'
        logger.error(error_text)
    except Exception as error:
        message = f'Program malfunction: {error}'
        logger.error(message)
        if message != previous_error:
            send_message(bot, message)
            previous_error = message
    time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
