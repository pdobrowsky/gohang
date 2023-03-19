import pandas as pd
import datetime as dt
import json
import collections
import calendar

from app import db, app
from app.models import User, Friend, Schedule, Hang

# !!!!!!need to update week of logic to account for year changeover in future

# clean up
# needs to process schedules to create possible hangs
# needs to write those results to new hangs table, update processed_at in schedule
# it runs every day (because you can update your schedule), but on Sundays it does the week ahead, rest of week it only does current week (for now)=
# ignore those already tried to schedule with since all on sms atm
# act as if hang is empty right now because it is, need to add to models
# going to need to have edit schedule eventually

# DB CONNECTION - Can I put this in the functions instead?
my_context = app.app_context()
my_context.push()
conn = db.engine.connect()
app.app_context()

def get_scope():
    # returns weekday and week to consider
    current_week = dt.datetime.utcnow().isocalendar().week
    weekday = dt.datetime.utcnow().weekday()
    is_sunday = weekday == 6 # scheduler targets the week ahead if it's Sunday

    if is_sunday:
        attempt_week = current_week + 1
        attempt_weekday = 0
    else:
        attempt_week = current_week
        attempt_weekday = weekday + 1

    return {'attempt_week':attempt_week,'attempt_weekday':attempt_weekday}

# DEFINING CONSTANTS FOR THE RUN
scope = get_scope()
attempt_week = scope['attempt_week']
attempt_weekday = scope['attempt_weekday']
fast_or_max = 'fast' # determines how aggressive the scheduler is. fast will try to move as many hangs to attempted as fast as possible but might send less slots, max will go slow to send the most slots
sms_slots = 3 # number of slots to send SMS users

weekday_filter = collections.defaultdict(dict) # a schedule that's intersected to clean up availability based on where we are in the week
empty_schedule = collections.defaultdict(dict) # a helper object in a lot of places

for time in ['Morning', 'Afternoon', 'Evening']:
    day_count = 0

    for day in calendar.day_name:
        empty_schedule[time][day] = False

        if day_count < attempt_weekday:
            weekday_filter[time][day] = False
        else:
            weekday_filter[time][day] = True

        day_count +=1

weekday_filter = pd.DataFrame.from_dict(weekday_filter)
empty_schedule = pd.DataFrame.from_dict(empty_schedule)

# HELPER FUNCTIONS
# moving more things to functions because I'm concerned about the modules being used outside of the cronjob where things are newly imported
def get_schedule(user_id):
    live_schedules = get_live_schedules()
    return live_schedules[live_schedules.user_id == user_id]

def get_live_schedules():
    schedules = pd.read_sql(Schedule.query.statement, conn)
    schedules['week_of'] = schedules['week_of_int']
    schedules = schedules[schedules['week_of'] == attempt_week] # will accept/expect multiple weeks in future?
    live_schedules_time = schedules.pivot_table(index=['user_id', 'week_of'], values=['created_at'], aggfunc=max) # needs to update for mutual hangs
    live_schedules_time.reset_index(inplace=True)

    if live_schedules_time.empty: # this line is kind of crap to avoid merge which will raise an error when there are no schedules
        return live_schedules_time

    live_schedules = schedules.merge(live_schedules_time, left_on=['user_id','week_of','created_at'], right_on=['user_id','week_of','created_at'], how='inner')

    return live_schedules

def sched_from_string(sched):
    return pd.DataFrame.from_dict(json.loads(sched))

def union_schedules(hangs):
    unioned_schedules = empty_schedule.copy()

    for index, row in hangs.iterrows():
        sched = sched_from_string(row.schedule)
        unioned_schedules = unioned_schedules | sched

    return unioned_schedules

def melt_schedule(sched):
    return pd.melt(sched.reset_index(), id_vars=['index'], value_vars=['Morning', 'Afternoon', 'Evening'])


# segment out two sets of friends, those that are communicated to through text and those that are done through 
# filter 1 directional set by user 2 being in hang (friend user id not creator)

# HANG friends
# This is not used yet
# add relation type to friend table

# SMS Friends - one direction


# WHO WILL HANG OUT - now lets do some pre-processing on the hangs to check how we're going to handle them
def get_friends_hangs():
    # ADD CALCULATE PRIORITY
    friends = pd.read_sql(Friend.query.statement, conn)
    hangs = pd.read_sql(Hang.query.statement, conn)
    confirmed_hangs = hangs[hangs.state == 'confirmed']
    recent_hangs = confirmed_hangs.pivot_table(index=['user_id_1', 'user_id_2'], 
                                                values=['week_of'], aggfunc=max).reset_index() # this needs to change when mutual hang friends gets introduced, friend_id

    # get when they last hung
    if not confirmed_hangs.empty:
        friends = friends.merge(recent_hangs[['week_of','user_id_1','user_id_2']], 
                                left_on=['creator_user_id', 'friend_user_id'], right_on=['user_id_1', 'user_id_2'], how='outer')
    else:
        friends['week_of'] = None

    friends['time_since_hang'] = attempt_week - friends['week_of']
    friends['attempt'] = friends.time_since_hang >= friends.cadence

    # figure out the state of hangs for the week
    current_state_hangs = hangs[hangs.week_of == attempt_week]

    if not current_state_hangs.empty:
        friends_hangs = friends.merge(current_state_hangs[['user_id_1', 'user_id_2','state']], left_on=['creator_user_id', 'friend_user_id'], right_on=['user_id_1', 'user_id_2'], how='left')
    else:
        friends_hangs = friends
        friends_hangs['state'] = None

    return friends_hangs

# cleanup friends to the ones you want to try and schedule

# LOG all the hangs to happen

# take every friend and make a new prospect for it 
# need to consider each week in future
def create_sms_hangs():
    counter = 0
    friends_hangs = get_friends_hangs()

    for index, row in friends_hangs.iterrows():
        if not row.state:
            if row.attempt or not row.time_since_hang == row.time_since_hang:
                used_schedule = get_schedule(row.creator_user_id)

                # does nothing if you have no schedule for the week
                if not used_schedule.empty:
                    # prioritizes friends you have not scheduled with yet over those you have (new friends it attempts next week)
                    if not row.attempt:
                        priority = 1 # value for friends that you have not yet hung with
                    else:
                        priority = 1 - (row.cadence/(row.time_since_hang + 1)) # value for friends that you have

                    hang_to_add = Hang(user_id_1= row.creator_user_id , user_id_2=row.friend_user_id, 
                                    state='prospect', week_of=attempt_week, priority=priority, schedule_id=int(used_schedule.id.iloc[0]))
                    
                    # consider getting rid of schedule ID since it's not used/updated?
                    db.session.add(hang_to_add)
                    counter += 1                    

    db.session.commit()

    print('added {} hangs'.format(counter))


def schedule_sms_hangs():
    hangs = pd.read_sql(Hang.query.statement, conn) # requery dataset in case, create_sms and schedule_sms are being run in same script
    users = pd.read_sql(User.query.filter_by(user_type='hang').statement, conn)

    for user_id in hangs.user_id_1.unique():
        used_schedule = get_schedule(user_id)
        attempt_slots = sms_slots

        # no schedule
        if used_schedule.empty:
            continue

        user_hangs = hangs[(hangs.user_id_1 == user_id) & (hangs.week_of == attempt_week)] # filter to hangs for the attempt week for the specific user

        # no hangs to try
        if user_hangs.empty:
            continue

        max_hangs = users.max_hang_per_week[users.id == user_id].values[0]
        planned_hangs = len(user_hangs[user_hangs.state.isin(['confirmed', 'accepted'])])

        # capped out
        if planned_hangs >= max_hangs:
            continue

        # get the schedules already booked
        in_flight_hangs = user_hangs[user_hangs.state.isin(['confirmed', 'accepted', 'attempted'])]
        current_schedule = sched_from_string(used_schedule.avails.values[0])

        if in_flight_hangs.empty:
            in_flight_schedule = empty_schedule.copy()
        else:
            in_flight_schedule = union_schedules(in_flight_hangs)

        not_booked = ~in_flight_schedule
        free_schedule = not_booked & weekday_filter & current_schedule

        # cadence should break priority ties in the future
        # retry declined hangs that want retry first, before new prospects, limits the number of people that are tried in one week
        user_hangs_retry = user_hangs[(user_hangs.state == 'declined') & (user_hangs.retry == True)]
        user_hangs_retry = user_hangs_retry.sort_values(by=['priority'], ascending=[False], ignore_index=True)

        print('retrying {} declined hangs'.format(len(user_hangs_retry)))
        for index, row in user_hangs_retry.iterrows():
            old_schedule = sched_from_string(row.schedule)
            retry_free_schedule = free_schedule & ~old_schedule # only try the slots not already tried

            # below this is the same as the new prospects?
            melted_sched = melt_schedule(retry_free_schedule)
            melted_sched = melted_sched[melted_sched.value == True]

            if melted_sched.empty:
                print('out of slots')
                break
            elif len(melted_sched) < sms_slots:
                if fast_or_max == 'max':
                    print('stopping to enforce max')
                    break
                else:
                    print('reducing slots to go fast')
                    attempt_slots = len(melted_sched)
            
            print('go')

            # create a schedule using the empty schedule, and update the free schedule
            top_slots = melted_sched[melted_sched.value == True].sample(attempt_slots) # in the future grab by value of the slots
            attempt_schedule = empty_schedule.copy()
            
            for index2, row2 in top_slots.iterrows():
                day = row2['index']
                time = row2['variable']

                attempt_schedule.at[day,time] = True
                free_schedule.at[day,time] = False

            hang_to_update = Hang.query.filter_by(id=row.id).first()
            hang_to_update.state = 'prospect' # this is the only difference from the new prospects
            hang_to_update.schedule = attempt_schedule.to_json()
            hang_to_update.updated_at = dt.datetime.utcnow()
            db.session.commit()

        # now do the new prospects
        user_hangs_prospects = user_hangs[(user_hangs.state == 'prospect')]
        user_hangs_prospects = user_hangs_prospects.sort_values(by=['priority'], ascending=[False], ignore_index=True)

        print('trying {} new prospects'.format(len(user_hangs_prospects)))
        for index, row in user_hangs_prospects.iterrows():
            melted_sched = melt_schedule(free_schedule)
            melted_sched = melted_sched[melted_sched.value == True]

            if melted_sched.empty:
                print('out of slots')
                break
            elif len(melted_sched) < sms_slots:
                if fast_or_max == 'max':
                    print('stopping to enforce max')
                    break
                else:
                    print('reducing slots to go fast')
                    attempt_slots = len(melted_sched)
            
            print('go')

            # create a schedule using the empty schedule, and update the free schedule
            top_slots = melted_sched[melted_sched.value == True].sample(attempt_slots)
            attempt_schedule = empty_schedule.copy()
            
            for index2, row2 in top_slots.iterrows():
                day = row2['index']
                time = row2['variable']

                attempt_schedule.at[day,time] = True
                free_schedule.at[day,time] = False

            hang_to_update = Hang.query.filter_by(id=row.id).first()
            hang_to_update.schedule = attempt_schedule.to_json()
            hang_to_update.updated_at = dt.datetime.utcnow()
            db.session.commit()