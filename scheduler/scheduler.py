import pandas as pd
import datetime as dt
import numpy as np
import json
import collections
import calendar
import math

from app import db, app
from app.models import User, Friend, Schedule, Hang
from sqlalchemy import or_, and_

# !!!!!!need to update week of logic to account for year changeover in future

# This is currently a Waterfall Scheduler, the goal is to schedule as many valuable hangs as possible with imperfect info we have about SMS users, while operating in sequence since we have limited availability
# Mutual vs SMS, Priority, "Day Value" are the primary inputs that are easy to imagine
# Over the total prospects for a week the goal is to max the priority scheduled; EV = pSchedule * priority
# But we don't currently have any expectation for pSchedule. It operates purely in order of Mutual > SMS, Higher Prio > Lower Prio
# this kind of works because pSchedule is 1 for mutuals if they have any overlap, so you'll just get more total value without holding up days in SMS attempt limbo
# pSchedule for SMS friendships is driven by a couple of things: the actual relationship, and the "value" of the days sent to them
# It randomly chooses days for both mutual and SMS avails. This will help learn for pSchedule, and is also easier, but it creates friction in a couple ways:
# optimal solving for mutuals: randomly choosing days and going in order of prio could lead to suboptimal scheduling choices, rather than finding the ideal allocation
# mutuals have pSchedule = 1 given that there's intersection, and so should actually take the days with LOWEST value to max pSchedule for SMS attempts
# with data about what days get scheduled in SMS convos, can learn what days will max pSchedule for SMS hangs to preserve them

# processes friendships and historical hangs to generate prospects for a week
# does mutuals first
# then sets up attempts for SMS
# could be nice to have it skip friends that were added within the current week (ie try the week after they're added)
# cadence should break priority ties in the future

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
# stuff with schedules
def get_schedule(user_id, attempt_week=attempt_week):
    schedule = pd.read_sql(Schedule.query.filter_by(week_of_int=attempt_week, user_id=user_id).order_by(Schedule.created_at.desc()).statement, conn)
    return schedule

def get_free_schedule(user_id):
    in_flight_hangs = pd.read_sql(Hang.query.filter_by(week_of=attempt_week).filter(or_(Hang.user_id_1 == user_id, Hang.user_id_2 == user_id)).statement, conn)
    in_flight_hangs = in_flight_hangs[in_flight_hangs.state.isin(['confirmed', 'accepted', 'attempted'])]

    if not get_schedule(user_id).empty:
        current_schedule = sched_from_string(get_schedule(user_id).avails.values[0])
    else:
        current_schedule = empty_schedule.copy()

    if in_flight_hangs.empty:
        in_flight_schedule = empty_schedule.copy()
    else:
        in_flight_schedule = union_schedules(in_flight_hangs)

    not_booked = ~in_flight_schedule
    free_schedule = not_booked & weekday_filter & current_schedule

    return free_schedule

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

def check_max_hangs(user_id):
    # check that the user has not reached their max hangs for the week
    max_hangs = User.query.filter_by(id=user_id).first().max_hang_per_week
    confirmed_hangs = Hang.query.filter_by(week_of=attempt_week).filter(or_(Hang.user_id_1 == user_id, Hang.user_id_2 == user_id),Hang.state.in_(['confirmed','accepted'])).all()
    if len(confirmed_hangs) >= max_hangs:
        return False
    else:
        return True

# segment out two sets of friends, those that are communicated to through text (1 way, but only one is hang) and those that are done through hang (mutual hang)
def get_mutual_friends():
    hang_users = pd.read_sql(User.query.filter_by(user_type='hang').statement, conn)

    # query friends for all rows where both users are hang users
    # find bi-directional: inner join where there is another row where creator/friend user ID are flipped
    # then drop duplicates of set(friend, creator) because we'll have two rows for each mutual friendship
    mutual_friends = pd.read_sql(Friend.query.filter(Friend.creator_user_id.in_(hang_users.id), Friend.friend_user_id.in_(hang_users.id)).statement, conn)
    mutual_friends = mutual_friends.merge(mutual_friends[['id', 'creator_user_id', 'friend_user_id', 'cadence']], 
                                          left_on=['creator_user_id', 'friend_user_id'], 
                                          right_on=['friend_user_id', 'creator_user_id'], 
                                          how='inner', suffixes=[None, '_y'])
    
    mutual_friends['set'] = mutual_friends[['creator_user_id', 'friend_user_id']].apply(lambda x: frozenset(x), axis=1)
    mutual_friends = mutual_friends.drop_duplicates(subset='set')
    mutual_friends['type'] = 'mutual'
    mutual_friends['schedule_cadence']  = np.maximum(mutual_friends.cadence, mutual_friends.cadence_y)
    mutual_friends['priority_cadence'] = np.minimum(mutual_friends.cadence, mutual_friends.cadence_y)

    return mutual_friends

def get_sms_friends():
    # would this be necessary if there was a relation to users table in friend table?
    hang_users = pd.read_sql(User.query.filter_by(user_type='hang').statement, conn)
    sms_users = pd.read_sql(User.query.filter_by(user_type='sms').statement, conn)

    friends = pd.read_sql(Friend.query.filter(Friend.creator_user_id.in_(hang_users.id), Friend.friend_user_id.in_(sms_users.id)).statement, conn)
    friends['set'] = friends[['creator_user_id', 'friend_user_id']].apply(lambda x: frozenset(x), axis=1)
    friends['type'] = 'sms'
    friends['schedule_cadence'] = friends.cadence
    friends['priority_cadence'] = friends.cadence

    return friends

# WHO WILL HANG OUT - we want to use the valid friendships and history of hangs to decide who to schedule
def get_friends_to_schedule():
    # put together the list of all valid friends
    mutual_friends = get_mutual_friends()
    sms_friends = get_sms_friends()
    all_friends = pd.concat([mutual_friends, sms_friends])

    # is it time to hang?
    confirmed_hangs = pd.read_sql(Hang.query.filter_by(state='confirmed').statement, conn)
    confirmed_hangs['set'] = confirmed_hangs[['user_id_1', 'user_id_2']].apply(lambda x: frozenset(x), axis=1)
    recent_hangs = confirmed_hangs.pivot_table(index='set', values='week_of', aggfunc=max).reset_index()

    if not confirmed_hangs.empty:
        # should I just use map for stuff like this?
        all_friends = all_friends.merge(recent_hangs[['week_of','set']], left_on='set', right_on='set', how='left')
    else:
        # this is only used in the case where there are no confirmed hangs
        all_friends['week_of'] = None

    all_friends['time_since_hang'] = attempt_week - all_friends['week_of']
    all_friends['attempt'] = (all_friends.time_since_hang >= all_friends.schedule_cadence) | all_friends.time_since_hang.isna()

    # have we done anything about it this week?
    current_week_hangs = pd.read_sql(Hang.query.filter_by(week_of=attempt_week).statement, conn)
    current_week_hangs['set'] = current_week_hangs[['user_id_1', 'user_id_2']].apply(lambda x: frozenset(x), axis=1)

    if not current_week_hangs.empty:
        friends_to_schedule = all_friends.merge(current_week_hangs[['set','state']], left_on='set', right_on='set', how='left')
    else:
        friends_to_schedule = all_friends
        friends_to_schedule['state'] = 'no_attempt'

    friends_to_schedule.state = friends_to_schedule.state.fillna('no_attempt')
    return friends_to_schedule

# Note to self: max hangs can be ignored right now because create doesn't look at it, and schedule only looks at the confirmed and accepted hangs
# create hang prospets and their priorities before attempting to schedule them
# creates all prospects that could feasibly be tried; so schedules are required to show up in the table for mutual friends
# do mutual friends stay prospects if their schedule doesn't intersect?
def create_hangs():
    counter = 0
    friends_hangs = get_friends_to_schedule()
    print('there are ' + str(len(friends_hangs)) + ' possible hangs to schedule')

    friends_hangs = friends_hangs[((friends_hangs.attempt) & (friends_hangs.state == 'no_attempt'))] # this language is confusing
    print('there are ' + str(len(friends_hangs)) + ' hangs that are valid to be added as prospects')

    for index, row in friends_hangs.iterrows():
        creator_schedule = get_schedule(row.creator_user_id)

        # I don't think this is working because it created prospects for me this week when I had no schedule
        if row.type == 'mutual':
            friend_schedule = get_schedule(row.friend_user_id)
            schedules_empty = creator_schedule.empty | friend_schedule.empty
        else:
            schedules_empty = creator_schedule.empty

        # only creates prospects if there's schedules available
        # basically if you don't have a schedule, you can't be scheduled, and we shouldn't judge scheduling effectiveness based on that
        if schedules_empty:
            print('skipping hang for user {} and friend {} because they have no schedule'.format(row.creator_user_id, row.friend_user_id))
            continue

        # what is the priority of the prospect?
        if math.isnan(row.time_since_hang):
            priority = .39 # value for friends that you have not yet hung with, if you are perfectly caught up then this will be at the top of the list, otherwise it will start to lose to those you've previously hung out with but are behind on
        else:
            priority = 1 - (row.priority_cadence/(row.time_since_hang + 1)) # value for friends that you have

        print('adding prospect for user {} and friend {} with priority {}'.format(row.creator_user_id, row.friend_user_id, priority))

        hang_to_add = Hang(user_id_1= row.creator_user_id , user_id_2=row.friend_user_id, 
                        state='prospect', week_of=attempt_week, priority=priority, friend_type=row.type)
        
        db.session.add(hang_to_add)
        counter += 1

    db.session.commit()
    print('added {} prospect hangs'.format(counter))

def schedule_mutual_hangs(mutual_hangs):
    for index, row in mutual_hangs.iterrows():
        # check that both users have not reached their max hangs for the week
        # if they have, then we can't schedule the hang and the state is still prospect
        if not check_max_hangs(row.user_id_1) or not check_max_hangs(row.user_id_2):
            print('skipping hang for user {} and friend {} because one has reached their max hangs'.format(row.user_id_1, row.user_id_2))
            continue

        # check for an intersection in schedules
        # if there is an intersection, then we can schedule the hang (just randomly choose the slot) and the state is accepted otherwise it is declined
        creator_schedule = get_free_schedule(row.user_id_1)
        friend_schedule = get_free_schedule(row.user_id_2)

        intersection = creator_schedule & friend_schedule
        if intersection.any().any():
            intersection = melt_schedule(intersection)
            intersection = intersection[intersection.value == True]
            slot = intersection.sample(1)

            day = slot['index'].values[0]
            time = slot['variable'].values[0]

            confirm_sched = empty_schedule.copy()
            confirm_sched.at[day,time] = True

            hang_to_update = Hang.query.filter_by(id=row.id).first()
            hang_to_update.state = 'accepted'
            hang_to_update.finalized_slot = day + ' ' + time
            hang_to_update.schedule = confirm_sched.to_json()
            hang_to_update.updated_at = dt.datetime.utcnow()
            db.session.commit()
            print('scheduled hang for user {} and friend {} at {} on {}'.format(row.user_id_1, row.user_id_2, time, day))
        else:
            hang_to_update = Hang.query.filter_by(id=row.id).first()
            hang_to_update.state = 'declined'
            hang_to_update.updated_at = dt.datetime.utcnow()
            db.session.commit()
            print('skipping hang for user {} and friend {} because they have no schedule intersection'.format(row.user_id_1, row.user_id_2))

def schedule_hangs():
    hangs = pd.read_sql(Hang.query.filter_by(week_of=attempt_week).order_by(Hang.priority.desc()).statement, conn)

    # go through the mutuals hangs first, then the sms hangs
    # the original loop doesn't work as well because we can't guarantee position of ID
    mutual_hangs = hangs[hangs.friend_type == 'mutual']
    mutual_hangs = mutual_hangs[mutual_hangs.state.isin(['prospect', 'declined'])] # we don't need to check retry for mutuals, we automatically retry them behind the scenes
    print('attempting to schedule {} mutual hangs'.format(len(mutual_hangs)))
    schedule_mutual_hangs(mutual_hangs)

    sms_hangs = hangs[hangs.friend_type == 'sms']
    sms_hangs = sms_hangs[sms_hangs.state.isin(['prospect', 'declined', 'auto_declined'])]
    print('attempting to schedule {} sms hangs'.format(len(sms_hangs)))

    for user_id in sms_hangs.user_id_1.unique():
        # get the schedules already booked
        free_schedule = get_free_schedule(int(user_id))
        attempt_slots = sms_slots
        user_hangs = sms_hangs[(sms_hangs.user_id_1 == user_id)] # filter to hangs for the attempt week for the specific user

        # no hangs to try
        if user_hangs.empty:
            print('user {} has no hangs to try'.format(user_id))
            continue
            
        # check if the user is at max hangs for the week
        # doing this only once means that it's possible to go above max I think
        if not check_max_hangs(int(user_id)):
            print('user {} is at max hangs for the week'.format(user_id))
            continue

        # retry declined hangs that want retry first, before new prospects, limits the number of people that are tried in one week
        user_hangs_retry = user_hangs[(user_hangs.state.isin(['declined', 'auto_declined'])) & (user_hangs.retry == True)]

        print('retrying {} declined hangs'.format(len(user_hangs_retry)))
        for index, row in user_hangs_retry.iterrows():
            old_schedule = sched_from_string(row.schedule)
            retry_free_schedule = free_schedule & ~old_schedule # only try the slots not already tried

            # below this is the same as the new prospects?
            melted_sched = melt_schedule(retry_free_schedule)
            melted_sched = melted_sched[melted_sched.value == True]

            if melted_sched.empty:
                print('out of slots for this user')
                continue
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