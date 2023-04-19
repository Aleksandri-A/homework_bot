import os
import sys
import logging
from http import HTTPStatus
import requests
import time
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


def check_tokens():
    """Проверка доступности переменных окружения."""
    if PRACTICUM_TOKEN is None:
        logger.critical('Переменная PRACTICUM_TOKEN не задана.')
        raise ValueError('Учетные данные не были предоставлены.')
    if TELEGRAM_TOKEN is None:
        logger.critical('Переменная TELEGRAM_TOKEN не задана.')
        raise ValueError('Учетные данные не были предоставлены.')
    if TELEGRAM_CHAT_ID is None:
        logger.critical('Переменная TELEGRAM_CHAT_ID не задана.')
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
    except Exception as error:
        logger.error(
            f'Ошибка при отправке запроса к эндпоинту API-сервиса: {error}'
        )
    if response.status_code != HTTPStatus.OK:
        status_code = response.status_code
        logger.error(f'Ответ с {ENDPOINT} не получен')
        raise ConnectionError(f'Неверный код статуса: {status_code}')
    logger.info('Отправка запроса успешно завершена. '
                'Получен корректный ответ.')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        logger.info('Некорректный ответ от API!')
        raise TypeError('Ответ не является словарем')
    homeworks = response.get('homeworks')
    current_date = response.get('current_date')
    if homeworks is None:
        raise ValueError('Ответ не содержит значение "homeworks"')
    if current_date is None:
        raise ValueError('Ответ не содержит значение "current_date"')
    if not isinstance(homeworks, list):
        logger.info('Значение "homeworks" не является списком!')
        raise TypeError('Ответ типа данных!')
    if not isinstance(current_date, int):
        logger.info('Значение "current_date" не является целым числом!')
        raise TypeError('Ошибка типа данных!')
    return True


def parse_status(homework):
    """Извлекает статус конкретной домашней работы."""
    try:
        homework_name = homework.get('homework_name')
        status = homework.get('status')
        if homework_name is None or status is None:
            logger.error('Ошибка при запросе данных - отсутствуют ключи.')
            raise TypeError(
                f'Ошибка получения данных homework_name:'
                f'{homework_name} и status: {status}'
            )
        verdict = HOMEWORK_VERDICTS[status]
    except Exception as error:
        logger.error(f'Неожиданный статус домашней работы: {error}')
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
            if check_response(response) is not True:
                logger.error('Получен невалидный ответ')
                continue
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
