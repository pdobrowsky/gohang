# data ingestion should be handled by each function?
import pandas as pd
import datetime as dt
import calendar

from app import db, app, sms_client
from app.models import User, Hang
from scheduler.scheduler import melt_schedule, sched_from_string, empty_schedule, get_scope

# DB CONNECTION
my_context = app.app_context()
my_context.push()
conn = db.engine.connect()

gohang_number = app.config['TWILIO_NUMBER']
admin_number = app.config['ADMIN_NUMBER']

attempt_body_base = """Hi {}! \U0001F44B Your friend {} was wondering whether you're free to hang at any of the below times this week \U0001F4C5\n{}\nIf you are, just reply with the number of your preferred time! Or N if none of them work.\n-Luna"""
confirm_body_base = """Confirmed! \U0001F4C5 You and {} are hanging on {}. Have fun! \U0001F37B \n-Luna"""
remind_body_base = """Hi! \U0001F44B Just a reminder that you and {} are hanging out on {}. Check in with them if you haven't already to finalize your plans. Have fun! \U0000E415 \n-Luna"""

accept_body_base = """Yay! \U0001F60D Confirming now! \n-Luna"""
decline_body_base = """Dang! \U0001F629 Would it be ok if tried to share some more times that might work? If it is, respond Y, otherwise you can just ignore this and I'll try again next week!\n-Luna"""
auto_decline_body = """Hi! \U0001F44B I haven't heard back from you, I'm going to assume you're busy or none of these times work, if you're still interested in hanging out this week, just respond to this message with Y and I'll try to find another time that works for both of you!\n-Luna"""
help_body = """\U0001F44B It looks like you need some help. \n\nPlease go to {}/contact to send a message to my developers! \U0001F929 \n-Luna""".format(app.config['URL'])
fail_body = """I'm sorry, I don't understand your message. If you're trying to respond to availability that was sent to you, try responding exactly like \'1\' or \'N\'. \n\nOr you might have encountered a bug :( \n\nIf you need help try saying \'Luna\'! I promise I'll be a smarter chatbot in the future \U0001F97A \n-Luna"""
retry_body = """Ok great! I'll send some more availability when I know more!\n-Luna"""

# HANDLERS FOR DIFFERENT RESPONSES
def send(message, number):
    sms_client.messages.create(
                body=message,
                from_=gohang_number,
                to=number)

def accept(hangs, message):
    new_schedule = empty_schedule.copy()
    avail = int(message)

    attempted_schedule = hangs.schedule
    attempted_schedule = melt_schedule(sched_from_string(attempted_schedule))
    slots = attempted_schedule[attempted_schedule.value == True]

    if avail > len(slots): # their message is not a valid slot
        return fail_body, None, None
    
    # change the accepted schedule to only have the accepted slot
    slot = slots.iloc[avail - 1]
    day = slot['index']
    time = slot['variable']
    new_schedule.at[day,time] = True

    hangs.state = 'confirmed' # NEED TO UPDATE THIS ONCE THERE IS SEPARATE CONFIRM LOGIC
    hangs.schedule = new_schedule.to_json()
    hangs.updated_at = dt.datetime.utcnow()
    hangs.finalized_slot = day + " " + time
    db.session.commit()

    return accept_body_base, day, time

def decline(hangs, type='manual'):
    if type == 'auto':
        hangs.state = 'auto_declined'
    else:
        hangs.state = 'declined'

    hangs.retry = False
    hangs.updated_at = dt.datetime.utcnow()
    db.session.commit()

    return decline_body_base

def retry(hangs):
    hangs.retry = True
    hangs.updated_at = dt.datetime.utcnow()
    db.session.commit()

    return retry_body

def remind():
    # send a reminder to both parties
    # this does not work for Monday, but I think that's ok for now because they'll only get scheduled on Sunday
    # if confirmed, reminded is false, is week of and the day is the day before the hang
    hangs = Hang.query.filter_by(reminded=False, state='confirmed', week_of=get_scope()['attempt_week']).all()
    current_day = dt.datetime.utcnow().weekday()
    tomorrow = current_day + 1
    tomorrow_string = calendar.day_name[tomorrow]

    for hang in hangs:
        if tomorrow_string in hang.finalized_slot:
            u1 = User.query.filter_by(id=hang.user_id_1).first()
            u2 = User.query.filter_by(id=hang.user_id_2).first()

            print("reminding {} and {} of their hang on {}".format(u1.first_name, u2.first_name, hang.finalized_slot))
            message = remind_body_base.format(u1.first_name, hang.finalized_slot)
            send(message, u2.phone_number)
            message = remind_body_base.format(u2.first_name, hang.finalized_slot)
            send(message, u1.phone_number)

            hang.reminded = True
            hang.updated_at = dt.datetime.utcnow()
            db.session.commit()

def handle_responses(sender, message):
    # should I move getting the user and hang to the top? Then better understand what is possible here before moving into the if statements
    user = User.query.filter_by(phone_number=sender).first()
    attempt_week = get_scope()['attempt_week']
    hangs = Hang.query.filter_by(user_id_2=user.id, week_of=attempt_week).filter(Hang.state.in_(['attempted','declined','auto_declined'])).first() # NEEDS TO BE UPDATED TO SUPPORT MORE THAN 1 USER, will fail if they have more than 1 hang in the same week
    and_confirm = 0

    if 'luna' in message.lower(): # should I make this a regex? help
        response = help_body
    elif hangs is None: # if they respond to a hang that doesn't exist
        response = fail_body
    else: # if they respond to a hang that exists
        if message == 'Y':
            # if they say yes check if they actually declined before, if so, set retry to true
            if hangs.state in ['declined','auto_declined']:
                response = retry(hangs)
            else:
                response = fail_body
        elif message == 'N':
            # is there something to decline?
            if hangs.state == 'attempted':
                response = decline(hangs)
            else:
                response = fail_body
        elif message.isdigit():
            response, day, time = accept(hangs, message)
            and_confirm = 1
        else:
            response = fail_body

    send(response, sender)

    # only works for no separate confirm logic and not multiple hangs per responding user
    if not response == fail_body:
        if and_confirm:
            u1 = User.query.filter_by(id=hangs.user_id_1).first() # the initiating user from hang app

            message = confirm_body_base.format(u1.first_name, day + " " + time)
            send(message, sender)
            message = confirm_body_base.format(user.first_name, day + " " + time)
            send(message, u1.phone_number)

def auto_decline():
    # function to auto decline hangs that have not been responded to
    # if attempted more than a day ago, auto decline and let the user know
    # will this work for multiple users? depends on how user_id_2 is set
    hangs = Hang.query.filter_by(state='attempted').all()
    print('checking {} hangs for auto decline'.format(len(hangs)))

    for hang in hangs:
        time_since_attempt = (dt.datetime.utcnow() - hang.updated_at).seconds
        print('hang {} was attempted {} seconds ago'.format(hang.id, time_since_attempt))
        if (dt.datetime.utcnow() - hang.updated_at).seconds > 90000: # 25 hours in seconds...kind of odd but I prefer if it doesn't randomly decline in the morning based on when the job runs
            print("auto declining hang {} for user {}".format(hang.id, hang.user_id_2))
            u2 = User.query.filter_by(id=hang.user_id_2).first()

            message = auto_decline_body
            send(message, u2.phone_number)

            decline(hang, type='auto')


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
def request_hangs():
    # future method to check what hangs are scheduled
    pass

def new():
    # future method to create new friend
    pass

def cancel():
    # future method to cancel a hang
    pass