import pandas as pd
import datetime as dt
import calendar

from app import db, app, sms_client
from app.models import User, Hang, Schedule, Conversation
from scheduler.scheduler import melt_schedule, sched_from_string, empty_schedule, get_scope

# DB CONNECTION
my_context = app.app_context()
my_context.push()
conn = db.engine.connect()

gohang_number = app.config['TWILIO_NUMBER']
admin_number = app.config['ADMIN_NUMBER']

# SMS TEMPLATES
# SCHEDULING
attempt_body_base = """Hi {}! \U0001F44B Your friend {} was wondering if you're free to hang at any of the below times this week \U0001F4C5\n{}\nIf you are, just reply with the number of your preferred time! Or N if none of them work.\n-Luna"""
confirm_body_base = """Confirmed! \U0001F4C5 You two are hanging on {}. Have fun! \U0001F37B \n-Luna"""
remind_body_base = """Hi! \U0001F44B Just a reminder that you two are hanging out on {}. Finalize your plans, and have fun! \U0000E415 \n-Luna"""
weekly_avails_reminder_body = """Hi {}! You haven't shared your availability for the coming week!\n\n \U0001F4C5 Please go to https://hangtime.herokuapp.com/create_schedule/{} to let me know when you're free so I can reach out to your friends! If you're not free, just ignore this message.\n-Luna"""

accept_body_base = """Yay! \U0001F60D Confirming now! \n-Luna"""
decline_body_base = """Dang! \U0001F629 Would it be ok if tried to share some more times that might work? If it is, respond Y!\n-Luna"""
auto_decline_body = """Hi! \U0001F44B I haven't heard back from you, I'm going to assume you're busy or none of these times work, if you're still interested in hanging out this week, just respond to this message with Y and I'll try to find another time that works for both of you!\n-Luna"""
help_body = """\U0001F44B It looks like you need some help. \n\nPlease go to {}/contact to send a message to my developers!\n-Luna""".format(app.config['URL'])
fail_body = """I'm sorry, I don't understand your message. If you're trying to respond to availability that was sent to you, try responding exactly like \'1\' or \'N\'. \n\nOr you might have encountered a bug :( \n\nIf you need help try saying \'Luna\'!"""
retry_body = """Great! I'll send some more availability when I know more!\n-Luna"""
no_retry_body = """Have a good week! \U0001F44B \n-Luna"""

# GROUP INTERACTIONS
# a base of a reminder
# a general help message
# a specific help message (what to do? what time?)
concierge_base_fail_response = """I don't think you two are hanging out this week, but if you'd like to do something just ask for an activity like \'Luna, what should we do for lunch?"\'"""
concierge_base_response = """You're hanging out on {}. You should figure out:\nWhat time?\nWhat to do? (dinner, drinks)\nWhere to go? (neighborhood, etc.)\n\nIf you need help, just say \'Luna, got any ideas?\'"""
concierge_specific_response = """\U0001F914 since it's {}, are you thinking {}? And since it's a {},  {}\n-Luna"""
concierge_suggestions = """\U0001f64c ok, {} I have some ideas! \n\nLoading..."""
concierge_create = """Hi, I'd love to help, make sure you've both signed up at https://hangtime.herokuapp.com/!"""

# building block responses, add emojis later
time_of_day = {"morning":{"emoji":"\U0001F305", 
                        "activities": "coffee, a workout, or brunch?"}, 
                "afternoon": {"emoji":"\U0001F31E", 
                            "activities": "lunch, a walk, or a museum?"}, 
                "evening": {"emoji": "\U0001F319",
                            "activities": "dinner, drinks, or a show?"}}

period_in_week = {"weekday": {"emoji": "\U0001F4C5", 
                      "response": "I'd also consider if you work near one another, and what time you start/get out of work"},
        "weekend": {"emoji": "\U0001F3C6",
                    "response": "I'd also consider how close by you live, and what time you wake up/go to bed"}}

# HANDLERS FOR DIFFERENT RESPONSES
def send(message, number):
    sms_client.messages.create(
                body=message,
                from_=gohang_number,
                to=number)
    
def group_send(message, numbers):
    # check twilio conversations api to see if there is already a conversation for this group
    numbers.sort()
    uid = ''.join(numbers)
    conversation = Conversation.query.filter_by(uid=uid).first()

    if conversation is None:
        # create a new conversation
        conversation = sms_client.conversations.v1.conversations.create(friendly_name=uid)
        sms_client.conversations.v1.conversations(conversation.sid).participants.create(identity='luna',messaging_binding_projected_address=gohang_number)

        for number in numbers:
            sms_client.conversations.v1.conversations(conversation.sid).participants.create(messaging_binding_address=number)

        conversation = Conversation(uid=uid, sid=conversation.sid)
        db.session.add(conversation)
        db.session.commit()

    sms_client.conversations.v1.conversations(conversation.sid).messages.create(body=message, author='luna')
    conversation.updated_at = dt.datetime.utcnow()
    db.session.commit()

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

    print('starting reminder process for {} hangs'.format(len(hangs)))

    for hang in hangs:
        if tomorrow_string in hang.finalized_slot:
            u1 = User.query.filter_by(id=hang.user_id_1).first()
            u2 = User.query.filter_by(id=hang.user_id_2).first()

            print("reminding {} and {} of their hang on {}".format(u1.first_name, u2.first_name, hang.finalized_slot))
            message = remind_body_base.format(hang.finalized_slot)
            group_send(message, [u2.phone_number, u1.phone_number])

            hang.reminded = True
            hang.updated_at = dt.datetime.utcnow()
            db.session.commit()

def confirm(hangs):
    pass
    # shoudl check scheudles are still accurate, not going over max hangs?
    # and then do the actual sending

def handle_responses(sender, message):
    # should I move getting the user and hang to the top? Then better understand what is possible here before moving into the if statements
    user = User.query.filter_by(phone_number=sender).first()
    attempt_week = get_scope()['attempt_week']
    hangs = Hang.query.filter_by(user_id_2=user.id, week_of=attempt_week).filter(Hang.state.in_(['attempted','declined','auto_declined'])).first() 
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
            elif hangs.state in ['declined','auto_declined']:
                response = no_retry_body
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

            message = confirm_body_base.format(day + " " + time)
            group_send(message, [u1.phone_number, sender])

def handle_group_responses(sender, message, recipient):
    # this function looks up the conversation based on the sender and recipient
    # this lets the function know which hang to use
    # it will use that to respond to the users, or have a default response if the hang/response doesn't exist

    # get all the data we need
    user_send = User.query.filter_by(phone_number=sender).first()
    user_receive = User.query.filter_by(phone_number=recipient).first()
    activities = ['coffee', 'a walk', 'lunch', 'a workout','brunch', 'a museuem', 'dinner', 'drinks', 'a show', 'happy hour', 'a movie', 'a concert', 'a hike', 'a run', 'a bike ride', 'a picnic', 'a game']
    found = False
    nums = [user_send.phone_number, user_receive.phone_number]
    nums.sort()
    uid = ''.join(nums)
    convo = Conversation.query.filter_by(uid=uid).first()
    attempt_week = get_scope()['attempt_week']
    hang_a_check = Hang.query.filter_by(user_id_2=user_send.id, user_id_1=user_receive.id, week_of=attempt_week).filter(Hang.state.in_(['confirmed'])).first() 
    hang_b_check = Hang.query.filter_by(user_id_1=user_send.id, user_id_2=user_receive.id, week_of=attempt_week).filter(Hang.state.in_(['confirmed'])).first() 
    hang = hang_a_check


    if convo is None: # do these two talk?
        send(concierge_create, sender)
        return
    if 'luna' not in message.lower(): # check for luna being mentioned
            return
    
    for activity in activities:     # check for activity
        if activity in message.lower():
            found = True
            group_send(concierge_suggestions.format(activity), [user_send.phone_number, user_receive.phone_number])

    if found: # found an activity, so exit
        return
    if hang_a_check is None: # check for a hang
        hang = hang_b_check
        if hang_b_check is None: # no hang
            group_send(concierge_base_fail_response, [user_send.phone_number, user_receive.phone_number])
            hang = None
            return
    if 'ideas' not in message.lower(): # check if asking for ideas
        group_send(concierge_base_response.format(hang.finalized_slot), [user_send.phone_number, user_receive.phone_number])
        return

    # respond with "ideas"/framing questions
    # response based on the time
    # get the time from the hang, then respond based on that
    slot = hang.finalized_slot
    day = slot.split(' ')[0]
    time = slot.split(' ')[1]

    # check if the day is a weekday or weekend
    # convert the day to a datetime object
    # then check if it is a weekday or weekend
    period_dict = {'Monday': 'weekday', 'Tuesday': 'weekday', 'Wednesday': 'weekday', 'Thursday': 'weekday', 'Friday': 'weekday', 'Saturday': 'weekend', 'Sunday': 'weekend'}
    hang_period = period_dict[day]
    period_emoji = period_in_week[hang_period]['emoji']
    period_response = period_in_week[hang_period]['response']

    # check if the time is morning, afternoon, or evening
    time_emoji = time_of_day[time.lower()]['emoji']
    time_response = time_of_day[time.lower()]['activities']

    group_send(concierge_specific_response.format(time.lower()+time_emoji, time_response, hang_period+period_emoji, period_response), [user_send.phone_number, user_receive.phone_number])

def auto_decline():
    # function to auto decline hangs that have not been responded to
    # if attempted more than a day ago, auto decline and let the user know
    # will this work for multiple users? depends on how user_id_2 is set
    hangs = Hang.query.filter_by(state='attempted', week_of=get_scope()['attempt_week']).all()
    print('checking {} hangs for auto decline'.format(len(hangs)))

    for hang in hangs:
        time_since_attempt = (dt.datetime.utcnow() - hang.updated_at).total_seconds()
        print('hang {} was attempted {} seconds ago'.format(hang.id, time_since_attempt))
        if (dt.datetime.utcnow() - hang.updated_at).total_seconds() > 90000: # 25 hours in seconds...kind of odd but I prefer if it doesn't randomly decline in the morning based on when the job runs
            print("auto declining hang {} for user {}".format(hang.id, hang.user_id_2))
            u2 = User.query.filter_by(id=hang.user_id_2).first()

            message = auto_decline_body
            send(message, u2.phone_number)

            decline(hang, type='auto')

def weekly_avails_reminder():
    # this function checks each hang user to see if they've set a schedule for the current week
    # if not, it sends them a reminder to do so
    # running this is triggered by run_weekly_avails_reminder once a week
    
    # only run on Sunday
    if get_scope()['attempt_weekday'] == 0:
        users = User.query.filter_by(user_type='hang').all()
        print('checking {} users for weekly avails'.format(len(users)))

        for user in users:
            # check if they have a schedule for the current week
            schedule = Schedule.query.filter_by(user_id=user.id, week_of_int=get_scope()['attempt_week']).first()
            if schedule is None:
                print('user {} has not set a schedule for the current week'.format(user.id))
                message = weekly_avails_reminder_body.format(user.first_name, get_scope()['attempt_week'])
                send(message, user.phone_number)

# PREP DATASET
def get_current_attempts():
    users = pd.read_sql(User.query.statement, conn)
    hangs = pd.read_sql(Hang.query.filter_by(friend_type='sms').statement, conn)
    attempt_week = get_scope()['attempt_week']

    attempt_hangs = hangs[(hangs.state == 'prospect') & (hangs.schedule.notnull()) & (hangs.week_of == attempt_week)]
    attempt_hangs = attempt_hangs.merge(users[['id','phone_number','first_name']], left_on='user_id_2', right_on='id', how='inner', suffixes=(None,'_y'))
    attempt_hangs = attempt_hangs[['id','user_id_1','user_id_2','schedule','phone_number','first_name','priority']]
    attempt_hangs = attempt_hangs.rename(columns={'first_name':'friend_name'})
    attempt_hangs = attempt_hangs.merge(users[['id','first_name']], left_on='user_id_1', right_on='id', how='inner', suffixes=(None,'_y'))
    attempt_hangs = attempt_hangs.rename(columns={'first_name':'sender_name'})
    attempt_hangs = attempt_hangs[['id','user_id_1','user_id_2','schedule','phone_number','friend_name','sender_name','priority']]
    attempt_hangs = attempt_hangs.sort_values(by='priority', ascending=False)

    return attempt_hangs

def attempt_new_prospects():
    print('starting attempts')
    attempt_hangs = get_current_attempts()
    attempt_week = get_scope()['attempt_week']

    # update this to be by user_id_2 to collate all friends trying to hang with them that week
    for index, row in attempt_hangs.iterrows():
        # Check if the SMS user already has a hang being scheduled, declined, or auto_declined for the given week
        existing_attempt = Hang.query.filter_by(user_id_2=row.user_id_2,week_of=attempt_week
                                                ).filter(
                                                    Hang.state.in_(['attempted', 'declined', 'auto_declined'])
                                                ).first()
        
        if existing_attempt:
            print('skipping sms attempt for user {} because they currently have a hang in state {}'.format(row.user_id_2, existing_attempt.state))
            continue

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

def confirm_mutuals():
    # take all the mutual hangs that have been accepted and send a confirmation message to each user
    hangs = Hang.query.filter_by(state='accepted', friend_type='mutual').all()

    print('starting confirmations for {} mutual hangs'.format(len(hangs)))
    for hang in hangs:
        u1 = User.query.filter_by(id=hang.user_id_1).first()
        u2 = User.query.filter_by(id=hang.user_id_2).first()

        message = confirm_body_base.format(hang.finalized_slot)
        group_send(message, [u2.phone_number, u1.phone_number])

        hang.state = 'confirmed'
        hang.updated_at = dt.datetime.utcnow()
        db.session.commit()
        print('sent confirmation for hang {}'.format(hang.id))

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