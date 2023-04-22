import logging
import os
import sys
import time
from http import HTTPStatus
from json.decoder import JSONDecodeError
import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    encoding='utf-8',
    format='%(asctime)s, %(levelname)s, '
           '%(message)s, %(name)s, %(filename)s, %(lineno)d'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, '
    '%(message)s, %(name)s, %(filename)s, %(lineno)d'
)
handler.setFormatter(formatter)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class HttpStatusException(Exception):
    """Не получен ожидаемый код статуса."""

    pass


class ApiResponseException(Exception):
    """Ошибка получения ответа с API."""

    pass


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    is_error = False
    for token_name, token in tokens.items():
        if token is None:
            logger.critical(f'Переменная {token_name} не задана.')
            is_error = True
    if is_error:
        raise ValueError('Учетные данные не были предоставлены.')


def send_message(bot, message):
    """
    Функция отправки сообщения.
    Отправляет сообщение в Telegram чат,
    определяемый переменной окружения TELEGRAM_CHAT_ID.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение {message} отправлено в чат')
    except Exception as error:
        logger.error(f'Ошибка при отправке {message}: {error}')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    PARAMS = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=PARAMS
        )
        if response.status_code != HTTPStatus.OK:
            raise HttpStatusException(
                f'Неверный код статуса: {response.status_code}'
            )
        result = response.json()
        if result.get('code') == 'UnknownError':
            raise ApiResponseException(
                f'API вернул ошибку: {result.get("error")}'
            )
        if result.get('code') == 'Not_authenticated':
            raise ApiResponseException(
                f'API вернул ошибку: {result.get("error")}'
            )
        return result
    except JSONDecodeError as error:
        raise ApiResponseException(
            f'Получен код 200, но JSON не может быть обработан: {error}'
        )
    except Exception as error:
        raise ApiResponseException(
            f'Ошибка получения ответа при обращении к {ENDPOINT}: {error}'
        )


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            'Некорректный ответ от API! Ответ не является словарем'
        )
    homeworks = response.get('homeworks')
    current_date = response.get('current_date')
    if homeworks is None:
        raise ValueError('Ответ не содержит значение "homeworks"')
    if current_date is None:
        raise ValueError('Ответ не содержит значение "current_date"')
    if not isinstance(homeworks, list):
        raise TypeError(
            'Некорректный ответ от API! '
            'Значение "homeworks" не является списком!'
        )
    if not isinstance(current_date, int):
        raise TypeError(
            'Некорректный ответ от API! '
            'Значение "current_date" не является целым числом!'
        )


def parse_status(homework):
    """Извлекает статус конкретной домашней работы."""
    if not isinstance(homework, dict):
        raise TypeError(
            'Некорректный ответ от API! Ответ не является словарем'
        )
    status = homework.get('status')
    if status is None or status not in HOMEWORK_VERDICTS.keys():
        raise TypeError(
            f'Ошибка получения данных status: {status}'
        )
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise TypeError(
            f'Ошибка получения данных homework_name: {homework_name}'
        )
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.info('Бот запущен.')
    timestamp = int(time.time())
    previos_error = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date')
            check_response(response)
            homeworks = response.get('homeworks')
            if len(homeworks) == 0:
                logger.debug('Отсутствие в ответе новых статусов')
            else:
                homework = homeworks[0]
                message = parse_status(homework)
                send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != previos_error:
                send_message(bot, message)
            previos_error = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
