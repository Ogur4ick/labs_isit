import matplotlib
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import telebot
import requests
import xml.dom.minidom

matplotlib.use('Agg')

bot = telebot.TeleBot('token')

CURRENCIES = {
    'USD': 'Доллар США',
    'EUR': 'Евро',
    'CNY': 'Китайский юань',
    'JPY': 'Японская иена',
    'TRY': 'Турецкая лира',
    'KZT': 'Казахстанский тенге'
}

keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
keyboard.add(*[telebot.types.KeyboardButton(name) for name in CURRENCIES.values()])


def get_rate_by_date(char_code, date_obj):
    try:
        formatted_date = date_obj.strftime('%d/%m/%Y')
        url = f'http://www.cbr.ru/scripts/XML_daily.asp?date_req={formatted_date}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        dom = xml.dom.minidom.parseString(response.text)
        dom.normalize()

        for valute in dom.getElementsByTagName('Valute'):
            if valute.getElementsByTagName('CharCode')[0].firstChild.data == char_code:
                nominal = int(valute.getElementsByTagName('Nominal')[0].firstChild.data)
                value = float(valute.getElementsByTagName('Value')[0].firstChild.data.replace(',', '.'))
                return value / nominal
        return None
    except Exception as e:
        print(f"Error getting rate: {e}")
        return None


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        '📊 Привет! Я бот для анализа курсов валют ЦБ РФ.\n'
        'Выбери валюту из меню ниже:',
        reply_markup=keyboard
    )


@bot.message_handler(func=lambda msg: msg.text in CURRENCIES.values())
def handle_currency(message):
    currency_name = message.text
    char_code = [k for k, v in CURRENCIES.items() if v == currency_name][0]

    msg = bot.send_message(
        message.chat.id,
        f'💱 Выбрана валюта: {currency_name}\n'
        '📅 Введите начальную и конечную даты в формате ДД.ММ.ГГГГ через пробел:'
    )
    bot.register_next_step_handler(msg, lambda m: process_dates(m, char_code))


def process_dates(message, char_code):
    try:
        bot.send_chat_action(message.chat.id, 'typing')

        if len(message.text.split()) != 2:
            raise ValueError("Нужно ввести две даты через пробел")

        start_str, end_str = message.text.split()
        start_date = datetime.strptime(start_str, '%d.%m.%Y')
        end_date = datetime.strptime(end_str, '%d.%m.%Y')

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        if (end_date - start_date).days > 30:
            bot.send_message(message.chat.id, '❌ Максимальный интервал - 30 дней')
            return

        dates, rates = [], []
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        progress_msg = bot.send_message(message.chat.id, '⏳ Собираю данные... 0%')

        for i in range(total_days):
            if rate := get_rate_by_date(char_code, current_date):
                dates.append(current_date)
                rates.append(rate)
            current_date += timedelta(days=1)

            if i % 3 == 0:
                bot.edit_message_text(
                    f'⏳ Собираю данные... {int((i + 1) / total_days * 100)}%',
                    message.chat.id,
                    progress_msg.message_id
                )

        if not dates:
            raise ValueError("Нет данных за указанный период")

        plt.style.use('ggplot')
        plt.figure(figsize=(10, 5))
        plt.plot(dates, rates, marker='o', linestyle='-', linewidth=2, markersize=8)
        plt.title(f'Курс {CURRENCIES[char_code]} ({char_code})\n{start_str} - {end_str}', pad=20)
        plt.xlabel('Дата', labelpad=15)
        plt.ylabel('Рублей за единицу', labelpad=15)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig('chart.png', dpi=120, bbox_inches='tight')
        plt.close()

        with open('chart.png', 'rb') as photo:
            bot.send_photo(message.chat.id, photo)
        bot.send_message(
            message.chat.id,
            f'📈 Статистика за период:\n'
            f'• Начальный курс: {rates[0]:.2f} руб.\n'
            f'• Конечный курс: {rates[-1]:.2f} руб.\n'
            f'• Изменение: {rates[-1] - rates[0]:+.2f} руб.'
        )

        bot.delete_message(message.chat.id, progress_msg.message_id)

    except ValueError as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {str(e)}')
    except Exception as e:
        bot.send_message(message.chat.id, f'⚠️ Произошла ошибка: {str(e)}')
        raise e


if __name__ == "__main__":
    bot.polling()
