import sys
import os
import requests
import time
import logging
from http import HTTPStatus

from telebot import TeleBot
from telebot.apihelper import ApiException
from telebot.apihelper import ApiTelegramException
from dotenv import load_dotenv
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
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}.'
        )
        raise EnvironmentError(
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}.'
        )
    return True


def send_message(bot, message):
    """Отправляет сообщение пользователю в чат Телеграмм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отправлено успешно: {message}.')
    except ApiException as e:
        logger.error(f'Возникла ошибка API Telebot: {e}')
    except requests.exceptions.RequestException as e:
        logger.error(f'Ошибка запроса: {e}')


def get_api_answer(timestamp):
    """Получаем данные по API."""
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
    keys = {'homeworks', 'current_date'}
    if not isinstance(response, dict):
        raise TypeError('Ожидался словарь с данными API.')
    for key in keys:
        if key not in response:
            raise KeyError(
                f'Обязательный ключ `{key}` отсутсвует в словаре API.'
            )
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Значение под ключом `homeworks` должно быть списком!')
    if not homeworks:
        raise ValueError('Список домашек пуст.')

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
            check_response(response)
            homework = response['homeworks']
            if not homework:
                logger.debug('Список с домашними заданиями пуст.')
                continue
            message = parse_status(homework[HOMEWORK_NUMBER])
            if message not in sended_message:
                send_message(bot, message)
                sended_message = message
            else:
                logger.info(
                    'Отмена отправки сообщения, данное сообщение '
                    'уже было отправлено: \n'
                    f'"{message}"'
                )
            timestamp = response.get('current_date', int(time.time()))
        except ApiTelegramException:
            logger.error(
                'Ошибка при отправке сообщения пользователю. (main)',
                exc_info=True
            )
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message, exc_info=True)
            if message not in sended_message:
                try:
                    send_message(bot, message)
                    sended_message = message
                except ApiTelegramException:
                    logger.error(
                        'Ошибка при отправке сообщения пользователю. (main)',
                        exc_info=True
                    )
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
