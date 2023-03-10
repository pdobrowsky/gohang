# data ingestion should be handled by each function?
import pandas as pd
import datetime as dt
import json
import collections
import calendar

from app import db, app, sms_client
from app.models import User, Friend, Schedule, Hang
from scheduler.scheduler import melt_schedule, sched_from_string, empty_schedule, get_scope, sms_slots

# DB CONNECTION
my_context = app.app_context()
my_context.push()
conn = db.engine.connect()

gohang_number = app.config['TWILIO_NUMBER']
admin_number = app.config['ADMIN_NUMBER']

attempt_body_base = """Hi {}! \U0001F44B Your friend {} was wondering whether you're free to hang at any of the below times this week \U0001F4C5\n{}\nIf you are, just reply with the number of your preferred time! Or N if none of them work.\n-Luna"""
accept_body_base = """Yay! \U0001F60D Confirming now! \n-Luna"""
decline_body_base = """Dang! \U0001F629 Maybe next time!\n-Luna"""
confirm_body_base = """Confirmed! \U0001F4C5 You and {} are hanging on {}. Have fun! \U0001F37B \n-Luna"""
remind_body_base = """Hello! This is a reminder that you and {} are planning to hang on {}. Have fun! \U0001F37B \n-Luna"""
help_body = """\U0001F44B It looks like you need some help. \n\nPlease go to {}/contact to send a message to my developers! \U0001F929 \n-Luna""".format(app.config['URL'])
fail_body = """I'm sorry, I don't understand your message. If you're trying to respond to availability that was sent to you, try responding exactly like \'1\' or \'N\'. \n\nOr you might have encountered a bug :( \n\nIf you need help try saying \'Luna\'! I promise I'll be a smarter chatbot in the future \U0001F97A \n-Luna"""

# HANDLERS FOR DIFFERENT RESPONSES
def send(message, number):
    sms_client.messages.create(
                body=message,
                from_=gohang_number,
                to=number)

def accept(sender, message, attempt_week):
    new_schedule = empty_schedule.copy()
    user = User.query.filter_by(phone_number=sender).first()
    hangs = Hang.query.filter_by(user_id_2=user.id, state='attempted', week_of=attempt_week).first()
    avail = int(message)

    attempted_schedule = hangs.schedule
    attempted_schedule = melt_schedule(sched_from_string(attempted_schedule))
    slots = attempted_schedule[attempted_schedule.value == True]

    if avail > len(slots): # it doesn't exist
        return fail_body, None, None, None
    
    slot = slots.iloc[avail - 1]
    day = slot['index']
    time = slot['variable']
    new_schedule.at[day,time] = True

    hangs.state = 'confirmed' # NEED TO UPDATE THIS ONCE THERE IS SEPARATE CONFIRM LOGIC
    hangs.schedule = new_schedule.to_json()
    hangs.updated_at = dt.datetime.utcnow()
    hangs.finalized_slot = day + " " + time
    db.session.commit()

    return accept_body_base, day, time, user
            
def hang_state_usable(sender, attempt_week):
    # checks if there are hangs to respond to
    user = User.query.filter_by(phone_number=sender).first()
    hangs = Hang.query.filter_by(user_id_2=user.id, state='attempted', week_of=attempt_week).all()

    if len(hangs) > 0:
        return True
    else:
        return False

def decline(sender,attempt_week):
    user = User.query.filter_by(phone_number=sender).first()
    hangs = Hang.query.filter_by(user_id_2=user.id, state='attempted', week_of=attempt_week).first() # NEEDS TO BE UPDATED TO SUPPORT MORE THAN 1 USER
    hangs.state = 'declined'
    hangs.updated_at = dt.datetime.utcnow()
    db.session.commit()

    return decline_body_base

def handle_responses(sender, message):
    attempt_week = get_scope()['attempt_week']
    and_confirm = 0

    if 'luna' in message.lower():
        response = help_body
    elif not hang_state_usable(sender, attempt_week):
        response = fail_body
    elif message == 'N':
        response = decline(sender, attempt_week)
    elif message.isdigit():
        response, day, time, user = accept(sender,message, attempt_week)
        and_confirm = 1
    else:
        response = fail_body

    send(response, sender)

    # only works for admin (just me) case and no separate confirm logic
    if not response == fail_body:
        if and_confirm:
            message = confirm_body_base.format('Paul', day + " " + time)
            send(message, sender)
            message = confirm_body_base.format(user.first_name, day + " " + time)
            send(message, admin_number)

# PREP DATASET
def get_current_attempts():
    users = pd.read_sql(User.query.statement, conn)
    hangs = pd.read_sql(Hang.query.statement, conn)
    attempt_week = get_scope()['attempt_week']

    attempt_hangs = hangs[(hangs.state == 'prospect') & (hangs.schedule.notnull()) & (hangs.week_of == attempt_week)]
    attempt_hangs = attempt_hangs.merge(users[['id','phone_number','first_name']], left_on='user_id_2', right_on='id', how='inner', suffixes=(None,'_y'))
    attempt_hangs = attempt_hangs[['id','user_id_1','user_id_2','schedule','phone_number','first_name']]
    attempt_hangs = attempt_hangs.rename(columns={'first_name':'friend_name'})
    attempt_hangs = attempt_hangs.merge(users[['id','first_name']], left_on='user_id_1', right_on='id', how='inner', suffixes=(None,'_y'))
    attempt_hangs = attempt_hangs.rename(columns={'first_name':'sender_name'})
    attempt_hangs = attempt_hangs[['id','user_id_1','user_id_2','schedule','phone_number','friend_name','sender_name']]

    return attempt_hangs

def attempt_new_prospects():
    print('starting attempts')
    attempt_hangs = get_current_attempts()

    # update this to be by user_id_2 to collate all friends trying to hang with them that week
    for index, row in attempt_hangs.iterrows():
        # prep the message
        schedule = melt_schedule(sched_from_string(row.schedule))
        schedule = schedule[schedule.value == True].reset_index()

        # construct schedule message
        schedule_message = ""
        num_slots = len(schedule)
        
        for option in range(1,num_slots+1):
            day = schedule.iloc[option-1]['index']
            time = schedule.iloc[option-1]['variable']
            schedule_message += "{}) {} {}\n".format(option, day, time)

        body = attempt_body_base.format(row.friend_name, row.sender_name, schedule_message)

        # send the message
        send(body,row.phone_number)
        
        hang_to_update = Hang.query.filter_by(id=row.id).first()
        hang_to_update.state = 'attempted'
        hang_to_update.updated_at = dt.datetime.utcnow()
        db.session.commit()
        print('sent attempt')

# FUTURE METHODS
def reminder():
    # send a reminder to both parties; punt
    # if confirmed, reminded is false, is week of and the day is the day before the hang
    pass

def request_hangs():
    # future method to check what hangs are scheduled
    pass

def new():
    # future method to create new friend
    pass

def cancel():
    # future method to cancel a hang
    pass