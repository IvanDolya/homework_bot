import logging
import os
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
import requests
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import ApiHomeworkError


load_dotenv()

logger = logging.getLogger(__name__)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
HOMEWORK_NUMBER = 0
MISSING_VARIABLE = 'Отсутствуют обязательные переменные окружения: '

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Возвращает True, если все переменные окружения на месте."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_tokens = [
        name for name, token in tokens.items() if not token
    ]
    if missing_tokens:
        logger.critical(
            f'{MISSING_VARIABLE}{", ".join(missing_tokens)}.'
        )
        raise EnvironmentError(
            f'{MISSING_VARIABLE}{", ".join(missing_tokens)}.'
        )


def send_message(bot, message):
    """Отправляет сообщение пользователю в чат Телеграмм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отправлено успешно: {message}.')
        return True
    except ApiException as e:
        logger.error(f'Возникла ошибка API Telebot: {e}')
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f'Ошибка запроса: {e}')
        return False


def get_api_answer(timestamp):
    """Получаем данные по API."""
    logger.info('Попытка получения данных по API')
    try:
        response = requests.get(
            url=ENDPOINT, headers=HEADERS, params={'from_date': timestamp}
        )
    except requests.RequestException as e:
        raise ConnectionError(
            f'Ошибка запроса к API. Получена ошибка: {e}.'
        ) from e

    if response.status_code != HTTPStatus.OK:
        raise ApiHomeworkError(
            f'Ошибка HTTP: статус-код - {response.status_code}. '
            f'Ожидался статус: {HTTPStatus.OK}'
        )
    try:
        response_data = response.json()
    except ValueError as e:
        raise ValueError('Ошибка декодирования JSON из ответа API') from e
    return response_data


def check_response(response):
    """Проверяет данные из словаря API."""
    key = 'homeworks'
    if not isinstance(response, dict):
        raise TypeError(f'Получен {type(response)} вместо ожидаемого словаря.')
    if key not in response:
        raise KeyError(
            f'Обязательный ключ `{key}` отсутсвует в словаре API.'
        )
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(f'Получен {type(homeworks)} вместо ожидаемого списка.')

    return homeworks


def parse_status(homework):
    """Получаем нужную информацию из ответа."""
    if not homework:
        raise ValueError('Пустой ответ от API Яндекс Домашка.')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None or homework_status not in HOMEWORK_VERDICTS:
        raise KeyError('Неверный формат данных для домашней работы.')
    verdict = HOMEWORK_VERDICTS.get(homework_status)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    sended_message = ''
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                logger.debug('Список с домашними заданиями пуст.')
                continue
            message = parse_status(homeworks[HOMEWORK_NUMBER])
            previous_timestamp = timestamp
            if not send_message(bot, message):
                sended_message = message
                timestamp = previous_timestamp
                logger.info(
                    'Отмена отправки сообщения, данное сообщение '
                    'уже было отправлено: \n'
                    f'"{message}"'
                )
            else:
                timestamp = response.get('current_date', int(time.time()))
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message, exc_info=True)
            if message != sended_message:
                send_message(bot, message)
                sended_message = message
        finally:
            logger.info(
                f'Ожидание следующего запроса -- {RETRY_PERIOD} секунд.'
            )
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    main()
