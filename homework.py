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
    level=logging.INFO)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.info('Сообщение отправлено')
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except error.TelegramError:
        logging.error('TELEGRAM_CHAT_ID недоступен')


def get_api_answer(current_timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
        if homework_statuses.status_code != HTTPStatus.OK:
            logging.error('API возвращает код, отличный от 200!')
            raise HomeworkException('API возвращает код, отличный от 200!')
    except ConnectionError:
        logging.error('Эндпоинт недоступен!')
        raise HomeworkException('Эндпоинт недоступен!')
    except Exception:
        logging.error('Сбой при запросе к эндпоинту!')
        raise HomeworkException('Сбой при запросе к эндпоинту!')
    response = homework_statuses.json()
    return response


def check_response(response):
    """Проверяет ответ API на корректность и выдает список домашек."""
    if response['homeworks'] is None:
        logging.error('Ключ словаря не найден!')
        raise HomeworkException('Ключ словаря не найден!')
    elif isinstance(response['homeworks'], list) is False:
        logging.error('Ответ API не вляется списком!')
        raise HomeworkException('Ответ API не вляется списком!')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашки и возвращает строчку для отправки."""
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    else:
        logging.error('Неизвестный статус домашки!')
        raise HomeworkException('Неизвестный статус домашки!')


def check_tokens():
    """Проверяет доступность переменных окружения."""
    if PRACTICUM_TOKEN is None:
        logging.critical(
            'Отсутствует обязательная переменная окружения: PRACTICUM_TOKEN'
        )
        return False
    elif TELEGRAM_TOKEN is None:
        logging.critical(
            'Отсутствует обязательная переменная окружения: TELEGRAM_TOKEN'
        )
        return False
    elif TELEGRAM_CHAT_ID is None:
        logging.critical(
            'Отсутствует обязательная переменная окружения: TELEGRAM_CHAT_ID'
        )
        return False
    return True


def main():
    """Основная логика работы бота."""
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks[0] is None:
                logging.error('Нет сообщения для отправки!')
                raise HomeworkException('Список домашек пуст!')
            send_message(bot, parse_status(homeworks[0]))
            current_timestamp = response['current_date']
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            time.sleep(RETRY_TIME)
        else:
            global time_sleep_error
            time_sleep_error = 30


if __name__ == '__main__':
    main()
