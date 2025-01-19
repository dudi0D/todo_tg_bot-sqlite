import sqlite3
from origamibot import OrigamiBot as Bot
from origamibot.listener import Listener
from origamibot.core.teletypes import ReplyKeyboardMarkup, KeyboardButton
from time import sleep


connection = sqlite3.connect('deals_of_users.db', check_same_thread=False)
cursor = connection.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT,
    admin             INTEGER,
    week_calendar_id  INTEGER REFERENCES calendar (week_calendar_id),
    tg_id             TEXT);''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS calendar (
    week_calendar_id INTEGER PRIMARY KEY AUTOINCREMENT,
    monday           TEXT,
    tuesday          TEXT,
    wednesday        TEXT,
    thursday         TEXT,
    friday           TEXT,
    saturday         TEXT,
    sunday           TEXT);''')
cursor.execute('CREATE TABLE IF NOT EXISTS weekly_calendar_id(max_id INTEGER);')
cursor.connection.commit()


def chars2time(text : str):
    for i in '., :-':
        if i in text and all(j for j in text.split(i) if j.isnumeric()) and len(text.split(i)) == 2:
            msg = text.split(i)
            return int(msg[0]) * 60 + int(msg[1])


def time2chars(time_in_int: int):
    hours = time_in_int // 60
    minutes = time_in_int % 60
    return f'{hours:02d}:{minutes:02d}'


def free_minutes(message):
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {message.text} (
    daily_task_id INTEGER PRIMARY KEY,
    tg_id                 REFERENCES users (tg_id),
    start_time    TEXT,
    end_time      TEXT,
    event_name TEXT);''')
    cursor.execute(f'SELECT * FROM {message.text} WHERE tg_id = \'{message.from_user.username}\'')
    output = cursor.fetchall()
    minutes_of_day = [0 for _ in range(1440)]
    starts_of_events = []
    ends_of_events = []
    for i in output:
        start_hour, start_minute = list(map(int, i[2].split(':')))
        starts_of_events.append(start_hour * 60 + start_minute)
        end_hour, end_minute = list(map(int, i[3].split(':')))
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
    cursor.connection.commit()
    return minutes_of_day


class BotCommands:
    def __init__(self, bot_obj: Bot):
        self.bot = bot_obj
        self.user_states = {} # for message processing
        self.user_id_count = 0 # for new users
        self.week_calendar_id_count = 0
        self.current_free_minutes = [0 for _ in range(1440)] # for new and existing events
        self.last_event_start_time = 0
        self.last_event_end_time = 0
        self.last_daily_task_id = 0
        self.weekly_calendar_id = 0
        self.current_new_event_day = ''
        self.last_event_name = ''
        self.tables = []
        self.sent_message_id = 0
        cursor.execute('SELECT MAX(id) FROM users')
        t = cursor.fetchall()[0][0]
        if t:
           self.week_calendar_id_count = t + 1
        else:
            self.week_calendar_id_count = 1
        self.user_id_count = self.week_calendar_id_count
        self.days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    def _refresh_existing_tables(self):
        cursor.execute('SELECT name FROM sqlite_schema WHERE name NOT LIKE "sqlite_%"')
        output = cursor.fetchall()
        existing_tables_of_week_days = []
        for i in output:
            if i[0] in self.days_of_week:
                existing_tables_of_week_days.append(i[0])
        self.tables = existing_tables_of_week_days

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
            sent_message = self.bot.send_message(chat_id, f'Welcome back, {users_name}! What would you like to do?', reply_markup=start_options)
            self.sent_message_id = sent_message.message_id

    def add_user(self, message):
        chat_id = message.chat.id
        name = message.text
        cursor.execute(
            "INSERT INTO users (id, name, admin, week_calendar_id, tg_id) VALUES (?, ?, ?, ?, ?)",
            (self.user_id_count, name, 0, self.week_calendar_id_count, message.from_user.username)
        )
        cursor.execute(
            "INSERT INTO calendar (week_calendar_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.week_calendar_id_count, "", "", "", "", "", "", "")
        )
        self.week_calendar_id_count += 1
        self.user_id_count += 1
        cursor.connection.commit()
        self.user_states[chat_id] = 0
        self.bot.send_message(chat_id, f"Welcome, {name}!")

    def edit_user_start(self, message):
        cursor.execute(f'SELECT name FROM users WHERE tg_id = \'{message.from_user.username}\'')
        self.bot.send_message(message.chat.id,f'Enter new user\'s name. Current is - {cursor.fetchall()[0][0]}')
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
        self._refresh_existing_tables()
        events_of_user = []
        for i in self.tables:
            cursor.execute(f'SELECT * FROM {i} WHERE tg_id = ?', (message.from_user.username, ))
            output = cursor.fetchall()
            for j in output:
                events_of_user.append(j+tuple([i]))
        print(events_of_user)

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
        self.current_free_minutes = free_minutes(message)
        self.current_new_event_day = message.text
        self.bot.send_message(message.chat.id, 'Enter event\'s name')
        self.user_states['new_event_name'] = 1

    def new_event_start(self, message):
        self.user_states['new_event_name'] = 0
        self.last_event_name = message.text
        self.bot.send_message(message.chat.id, 'Enter event\'s start time\nFor example:13.00')
        self.user_states['new_event_start'] = 1

    def new_event_end(self, message):
        if chars2time(message.text):
            self.last_event_start_time = chars2time(message.text)
            self.bot.send_message(message.chat.id, "Enter event's end time\nFor example:14.25")
            self.user_states['new_event_end'] = 1
            self.user_states['new_event_start'] = 0
        else:
            self.bot.send_message(message.chat.id, 'Entered time is in incorrect form. Please, try again')

    def new_event_finished(self, message):
        self.last_event_end_time = chars2time(message.text)
        times = [self.last_event_start_time, self.last_event_end_time]
        time_period_of_event = range(min(times), max(times)+1)
        self.user_states['new_event_end'] = 0
        for i in time_period_of_event:
            if self.current_free_minutes[i-1] == 1:
                self.user_states['new_event_start'] = 1
                self.bot.send_message(message.chat.id, 'The entered interval is unavailable.\nTry another')
                return
        else:
            cursor.execute('SELECT * FROM weekly_calendar_id')
            output = cursor.fetchall()
            if not output:
                cursor.execute('INSERT INTO weekly_calendar_id (max_id) VALUES (0)')
                cursor.execute('SELECT * FROM weekly_calendar_id')
            self.weekly_calendar_id = list(output)[0][0]
            self.weekly_calendar_id += 1
            cursor.execute(f'INSERT INTO {self.current_new_event_day} (daily_task_id, tg_id, start_time, end_time, event_name) '
                           f'VALUES (?, ?, ?, ?, ?)', (self.weekly_calendar_id, message.from_user.username,
                                                    time2chars(self.last_event_start_time),
                                                    time2chars(self.last_event_end_time),
                                                    self.last_event_name))
            cursor.execute(f'UPDATE weekly_calendar_id SET max_id = {self.weekly_calendar_id}')
            cursor.connection.commit()
            self.bot.send_message(message.chat.id, 'Event was successfully added')


class MessageListener(Listener):
    def __init__(self, bot_obj, commands):
        self.bot = bot_obj
        self.commands = commands
        self.message_count = 0
        self.days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        self.commands_on_start = {'Change user\'s name': self.commands.edit_user_start,
                             'Create an event': self.commands.new_event, 'Edit an event': self.commands.edit_event}

    def on_message(self, message):
        self.message_count += 1
        chat_id = message.chat.id
        if message.text in self.commands_on_start:
            self.commands_on_start[message.text](message)
        elif self.commands.user_states.get('edit_name') == 1:
            self.commands.edit_user_continue(message)
        elif self.commands.user_states.get(chat_id) == 1:
            self.commands.add_user(message)
        elif message.text in self.days_of_week:
            self.commands.new_event_name(message)
        elif self.commands.user_states.get('new_event_name') == 1:
            self.commands.new_event_start(message)
        elif self.commands.user_states.get('new_event_start') == 1:
            self.commands.new_event_end(message)
        elif self.commands.user_states.get('new_event_end') == 1:
            self.commands.new_event_finished(message)


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
