import sqlite3
from origamibot import OrigamiBot as Bot
from origamibot.listener import Listener
from origamibot.core.teletypes import ReplyKeyboardMarkup, KeyboardButton
from time import sleep


connection = sqlite3.connect('deals_of_users.db', check_same_thread=False)
cursor = connection.cursor()


def free_minutes(message):
    cursor.execute(f'CREATE TABLE IF NOT EXISTS {message.text}('
                   f'user_id INT,'
                   f'start_time VARCHAR(100),'
                   f'end_time VARCHAR(100))')
    cursor.execute(f'SELECT * FROM {message.text} WHERE user_id = \'{message.from_user.username}\'')
    output = cursor.fetchall()
    minutes_of_day = [0 for _ in range(1440)]
    starts_of_events = []
    ends_of_events = []
    for i in output:
        start_hour, start_minute = list(map(int, i[1].split('.')))
        starts_of_events.append(start_hour * 60 + start_minute)
        end_hour, end_minute = list(map(int, i[2].split('.')))
        ends_of_events.append(end_hour * 60 + end_minute)
    starts_of_events.sort()
    ends_of_events.sort()
    event = 0
    for i in range(1440):
        if i in starts_of_events:
            event = 1
        if i in ends_of_events:
            event = 0
        minutes_of_day[i] += 1 * event
    return minutes_of_day


class BotCommands:
    def __init__(self, bot_obj: Bot):
        self.bot = bot_obj
        self.user_states = {}
        self.last_event_name = ''
        self.last_event_start_time = 0
        self.last_event_end_time = 0
        cursor.execute('SELECT MAX(id) FROM users')
        t = cursor.fetchall()[0][0]
        if t:
           self.week_calendar_id_count = t + 1
        else:
            self.week_calendar_id_count = 1
        self.user_id_count = self.week_calendar_id_count
        self.days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    def start(self, message):
        chat_id = message.chat.id
        cursor.execute('SELECT tg_id FROM users')
        cursor_output = cursor.fetchall()
        existing_tg_ids = [i[0] for i in set(cursor_output)]
        if message.from_user.username not in existing_tg_ids:
            self.user_states[chat_id] = 1
            self.bot.send_message(chat_id, 'Hi! What is your name?')
        else:
            start_options = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Change user's name")],
                    [KeyboardButton(text="Create an event")],
                    [KeyboardButton(text="Edit an event")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            cursor.execute('SELECT * FROM users')
            cursor_output = cursor.fetchall()
            users_name = ''
            for i in cursor_output:
                if message.from_user.username in i:
                    users_name = i[1]
                    break
            self.bot.send_message(chat_id, f'Welcome back, {users_name}! What would you like to do?', reply_markup=start_options)

    def add_user(self, message):
        global week_calendar_id_count, user_id_count
        chat_id = message.chat.id
        name = message.text
        cursor.execute(
            "INSERT INTO users (id, name, admin, week_calendar_id, tg_id) VALUES (?, ?, ?, ?, ?)",
            (user_id_count, name, 1, week_calendar_id_count, message.from_user.username)
        )
        cursor.execute(
            "INSERT INTO calendar (week_calendar_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (week_calendar_id_count, "", "", "", "", "", "", "")
        )
        week_calendar_id_count += 1
        user_id_count += 1
        cursor.connection.commit()
        self.user_states[chat_id] = 0
        self.bot.send_message(chat_id, f"Welcome, {name}!")

    def edit_user_start(self, message):
        cursor.execute(f'SELECT name FROM users WHERE tg_id = \'{message.from_user.username}\'')
        self.bot.send_message(message.chat.id, f'Enter new user\'s name. Current is - {cursor.fetchall()[0][0]}')
        self.user_states['edit_name'] = 1

    def edit_user_continue(self, message):
        cursor.execute(f"UPDATE users SET name = '{message.text}' WHERE tg_id = '{message.from_user.username}'")
        cursor.connection.commit()
        self.bot.send_message(message.chat.id, 'Changes were made')
        self.user_states['edit_name'] = 0

    def new_event(self, message):
        buttons = [[KeyboardButton(text=i) for i in self.days_of_week]]
        day_options = ReplyKeyboardMarkup(
            keyboard=buttons,
            resize_keyboard=True,
            one_time_keyboard=True
        )
        self.bot.send_message(message.chat.id, "Choose a day", reply_markup=day_options)

    def edit_event(self, message): # To do
        pass

    def database_users(self, message):
        chat_id = message.chat.id
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        response = "\n".join([str(user) for user in users])
        self.bot.send_message(chat_id, response)

    def database_calendar(self, message):
        chat_id = message.chat.id
        cursor.execute("SELECT * FROM calendar")
        calendars = cursor.fetchall()
        response = "\n".join([str(row) for row in calendars])
        self.bot.send_message(chat_id, response)

    def new_event_name(self, message):
        free_minutes(message)
        self.bot.send_message(message.chat.id, 'Enter event\'s name')
        self.user_states[message.text+'_start'] = 1


    def new_event_start(self, message):
        self.last_event_name = message.text
        self.bot.send_message(message.chat.id, 'Enter event\'s start time\nFor example:13.00')
        # self.user_states[]
        self.user_states[self.last_event_name+'_time1'] = 1


class MessageListener(Listener):
    def __init__(self, bot_obj, commands):
        self.bot = bot_obj
        self.commands = commands
        self.message_count = 0
        self.days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        self.commands_on_start = {'Change user\'s name': self.commands.edit_user_start,
                             'Create an event': self.commands.new_event, 'Edit an event': self.commands.edit_event}
        self.days_of_start = [i+'_start' for i in self.days_of_week]
        self.days_of_time_start = [i+'_time1' for i in self.days_of_week]
        self.days_of_time_end = [i+'_time2' for i in self.days_of_week]

    def on_message(self, message):
        self.message_count += 1
        chat_id = message.chat.id
        if message.text in self.commands_on_start:
            self.commands_on_start[message.text](message)
        elif 'edit_name' in self.commands.user_states and self.commands.user_states['edit_name'] == 1:
            self.commands.edit_user_continue(message)
        elif chat_id in self.commands.user_states and self.commands.user_states[chat_id] == 1:
            self.commands.add_user(message)
        elif message.text in self.days_of_week:
            self.commands.new_event_name(message)
            print(self.commands.user_states.keys())
        elif any(key in self.days_of_start for key in self.commands.user_states.keys()):
            self.commands.new_event_start(message)
        elif any(key in self.days_of_time_start for key in self.commands.user_states.keys()):
            self.commands.new_event_start(message)


if __name__ == '__main__':
    with open('token.txt') as f:
        token = f.read()
    bot = Bot(token)
    bot_commands = BotCommands(bot)
    bot.add_listener(MessageListener(bot, bot_commands))
    bot.add_commands(bot_commands)
    bot.start()
    while True:
        sleep(1)
