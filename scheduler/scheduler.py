import pandas as pd
import datetime as dt
import json

from app import db, app
from app.models import User, Friend, Schedule, Hang

# clean up
# needs to process schedules to create possible hangs
# needs to write those results to new hangs table, update processed_at in schedule
# it runs every day (because you can update your schedule), but on Sundays it does the week ahead, rest of week it only does current week (for now)=
# ignore those already tried to schedule with since all on sms atm
# act as if hang is empty right now because it is, need to add to models

# establish context and db connection
my_context = app.app_context()
my_context.push()
conn = db.engine.connect()

# base data ingestion
u = User.query.filter_by(user_type="hang")
f = Friend.query
s = Schedule.query
h = Hang.query

users = pd.read_sql(u.statement, conn)
friends = pd.read_sql(f.statement, conn)
schedules = pd.read_sql(s.statement, conn)
hangs = pd.read_sql(h.statement, conn)

# some constants for the run
sms_slots = 2 # number of slots to send SMS users
current_week = dt.datetime.utcnow().isocalendar().week
weekday = dt.datetime.utcnow().weekday()
is_sunday = weekday == 6

if is_sunday:
    attempt_week = current_week + 1
    attempt_weekday = 0
else:
    attempt_week = current_week
    attempt_weekday = weekday + 1

# segment out two sets of friends, those that are communicated to through text and those that are done through 
# filter 1 directional set by user 2 being in hang (friend user id not creator)

# HANG friends
# This is not used yet
# add relation type to friend table

# SMS Friends - one direction
friends = friends # for now, eventually will be the inverse of the above


# now lets do some pre-processing on the hangs to check how we're going to handle them
confirmed_hangs = hangs[hangs.state == 'confirmed']
recent_hangs = confirmed_hangs.pivot_table(index=['user_id_1', 'user_id_2'], 
                                            values=['week_of'], aggfunc=max).reset_index(inplace=True) # this needs to change when mutual hang friends gets introduced, friend_id

# get when they last hung
if not confirmed_hangs.empty:
    friends = friends.merge(recent_hangs.week_of, 
                            left_on=['creator_user_id', 'friend_user_id'], right_on=['user_id_1', 'user_id_2'], how='inner')
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

# cleanup friends to the ones you want to try and schedule

# prep schedules to be considered
schedules['week_of'] = schedules['week_of'].apply(lambda x: x.isocalendar().week)
schedules = schedules[schedules['week_of'] == attempt_week] # will accept/expect multiple weeks in future?
live_schedules_time = schedules.pivot_table(index=['user_id', 'week_of'], values=['created_at'], aggfunc=max) # needs to update for mutual hangs
live_schedules_time.reset_index(inplace=True)
live_schedules = schedules.merge(live_schedules_time, left_on=['user_id','week_of','created_at'], right_on=['user_id','week_of','created_at'], how='inner')

# check for more recent schedule updates to make? Or could make model improvements to schedule to only have current ones in future
def get_schedule(user_id):
    return live_schedules[live_schedules.user_id == user_id]

# LOG all the hangs to happen
# take every friend and make a new attempt for it 
# need to consider each week in future
def create_sms_hangs():
    counter = 0

    for index, row in friends_hangs.iterrows():
        if not row.state:
            if row.attempt or not row.time_since_hang == row.time_since_hang:
                used_schedule = get_schedule(row.creator_user_id)
                # need to set priority intelligently in the future

                if not used_schedule.empty:
                    hang_to_add = Hang(user_id_1= row.creator_user_id , user_id_2=row.friend_user_id, 
                                    state='prospect', week_of=attempt_week, priority=1.0000, schedule_id=int(used_schedule.id.iloc[0]))
                    
                    # for any in the current week that are still in prospect, should also update schedule ID to be used schedule
                    
                    db.session.add(hang_to_add)
                    counter += 1
                    

    db.session.commit()
    print('added {} hangs'.format(counter))