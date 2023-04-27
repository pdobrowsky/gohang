from flask import render_template, flash, redirect, request, url_for
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db, messager, scheduler
from app.forms import LoginForm, SignUpForm, EditProfileForm, ResetPasswordRequestForm, ResetPasswordForm, EmptyForm, FriendForm, ScheduleForm, ContactForm, EditFriendForm
from wtforms import BooleanField
from app.models import User, Friend, Schedule
from app.emails import send_password_reset_email
from datetime import datetime
from json import dumps, loads
from twilio.twiml.messaging_response import MessagingResponse

import collections

# coloring hangs 
colors = {"prospect":"active", "confirmed":"success", "attempted":"info", "declined":"warning", "auto_declined":"warning", "canceled":"danger"}

def add_friend(form):
    user = User.query.filter_by(phone_number=form.phone_number.data).first()

    if user is None:
        user = User(phone_number=form.phone_number.data, first_name=form.name.data)
        db.session.add(user)
        db.session.commit()
        user = User.query.filter_by(phone_number=form.phone_number.data).first()
    elif user == current_user: 
        flash('You can\'t friend yourself!')
        return None
    elif current_user.is_friend(user):
        flash('You\'ve already added {} as a friend!'.format(form.name.data))
        return None
    elif form.phone_number.data == app.config['TWILIO_NUMBER']:
        flash('You can\'t friend our chatbot Luna!')
        return None

    friend = Friend(creator_user_id=current_user.id, friend_user_id=user.id, cadence=form.cadence.data, provided_name=form.name.data)
    db.session.add(friend)
    db.session.commit()
    flash('Added {} as a friend!'.format(form.name.data))

@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = FriendForm()

    # note, this does not use the provided name, but the name they enter if they join the app, which doesn't match what's shown in the friends list
    hangs = current_user.upcoming_hangs(scheduler.get_scope()['attempt_week'])

    if form.validate_on_submit():
        add_friend(form)
        return redirect(url_for('index'))

    return render_template('index.html', title='Home', form=form, hangs=hangs, colors=colors)

@app.route('/friends', methods=['GET','POST'])
@login_required
def friends():
    form = FriendForm()
    friends = Friend.query.filter_by(creator_user_id=current_user.id)

    to_friend = current_user.non_mutual_friends()

    if form.validate_on_submit():
        add_friend(form)
        return redirect(url_for('friends'))

    return render_template('friends.html', title='Friends', form=form, friends=friends, to_friend=to_friend)

@app.route('/unfriend/<id>', methods=['GET'])
@login_required
def unfriend(id):
    user = User.query.filter_by(id=id).first()

    if user is None:
        flash('User {} not found.'.format(id))
        return redirect(url_for('friends'))
    if user == current_user:
        flash('You can\'t unfriend yourself!')
        return redirect(url_for('friends'))
    if not current_user.is_friend(user):
        flash('You are not friends with {}'.format(id))
        return redirect(url_for('friends'))
    
    friend = Friend.query.filter_by(creator_user_id=current_user.id, friend_user_id=id).first()
    name = friend.provided_name
    
    db.session.delete(friend)
    db.session.commit()
    
    flash('You unfriended {}'.format(name))

    return redirect(url_for('friends'))

@app.route('/edit_friend/<id>', methods=['GET','POST'])
@login_required
def edit_friend(id):
    user = User.query.filter_by(id=id).first()

    if user is None:
        flash('User {} not found.'.format(id))
        return redirect(url_for('friends'))
    if user == current_user:
        flash('You can\'t change your friendship with yourself!')
        return redirect(url_for('friends'))
    if not current_user.is_friend(user):
        flash('You are not friends with {}'.format(id))
        return redirect(url_for('friends'))

    form = EditFriendForm()
    friend = Friend.query.filter_by(creator_user_id=current_user.id, friend_user_id=id).first()

    if form.validate_on_submit():
        friend.cadence = form.cadence.data
        friend.provided_name = form.name.data
        friend.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Updated friendship with {}'.format(friend.provided_name))
        return redirect(url_for('friends'))
    elif request.method == 'GET':
        form.name.data = friend.provided_name
        form.cadence.data = friend.cadence

    return render_template('edit_friend.html', title='Edit Friend', form=form)

@app.route('/schedule', methods=['GET','POST'])
@login_required
def schedule():
    form = ScheduleForm()
    current = scheduler.get_scope()['attempt_week']
    next = scheduler.get_scope()['attempt_week'] + 1
    current_schedule = scheduler.get_schedule(current_user.id, current)
    next_schedule = scheduler.get_schedule(current_user.id, next)

    if form.validate_on_submit():
        avails = collections.defaultdict(dict)

        for time in ['Morning', 'Afternoon', 'Evening']:
            for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
                avails[time][day] = getattr(form, time+day).data

        avails = dumps(avails)

        schedule = Schedule(user_id = current_user.id, week_of_int = int(form.week.data[-2:]), avails=avails)
        db.session.add(schedule)
        db.session.commit()

        flash("Your schedule for the week of {} was added! :D".format(form.week.data))
        redirect(url_for('schedule'))

    return render_template('schedule.html', title='Availability', form=form, current_schedule=current_schedule, next_schedule=next_schedule, current=current, next=next)

@app.route('/edit_schedule/<id>', methods=['GET','POST'])
@login_required
def edit_schedule(id):
    schedule = Schedule.query.filter_by(id=id).first()
    current = scheduler.get_scope()['attempt_week']
    next = scheduler.get_scope()['attempt_week'] + 1
    current_schedule = scheduler.get_schedule(current_user.id, current)
    next_schedule = scheduler.get_schedule(current_user.id, next)

    if schedule is None:
        flash('Schedule {} not found.'.format(id))
        return redirect(url_for('schedule'))
    if schedule.user_id != current_user.id:
        flash('You can\'t edit someone else\'s schedule!')
        return redirect(url_for('schedule'))

    form = ScheduleForm()
    avails = loads(schedule.avails)

    if form.validate_on_submit():
        avails = collections.defaultdict(dict)

        for time in ['Morning', 'Afternoon', 'Evening']:
            for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
                avails[time][day] = getattr(form, time+day).data

        avails = dumps(avails)

        schedule.avails = avails
        schedule.week_of_int = int(form.week.data[-2:])
        schedule.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Updated schedule for the week of {}'.format(form.week.data))
        return redirect(url_for('schedule'))
    elif request.method == 'GET':
        form.week.data = '2023-W' + str(schedule.week_of_int).zfill(2) # need to correct for year change...evntually
        for time in ['Morning', 'Afternoon', 'Evening']:
            for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
                setattr(getattr(form, time+day), 'data', avails[time][day])

    return render_template('schedule.html', title='Schedule', form=form, current_schedule=current_schedule, next_schedule=next_schedule, current=current, next=next)

@app.route('/create_schedule/<week>', methods=['GET','POST'])
@login_required
def create_schedule(week):
    form = ScheduleForm()
    current = scheduler.get_scope()['attempt_week']
    next = scheduler.get_scope()['attempt_week'] + 1
    current_schedule = scheduler.get_schedule(current_user.id, current)
    next_schedule = scheduler.get_schedule(current_user.id, next)

    if form.validate_on_submit():
        avails = collections.defaultdict(dict)

        for time in ['Morning', 'Afternoon', 'Evening']:
            for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
                avails[time][day] = getattr(form, time+day).data

        avails = dumps(avails)

        schedule = Schedule(user_id = current_user.id, week_of_int = int(form.week.data[-2:]), avails=avails)
        db.session.add(schedule)
        db.session.commit()

        flash("Your schedule for the week of {} was added! :D".format(form.week.data))
        return redirect(url_for('schedule'))
    elif request.method == 'GET':
        form.week.data = '2023-W' + str(week).zfill(2) # need to correct for year change...evntually

    return render_template('schedule.html', title='Schedule', form=form, current_schedule=current_schedule, next_schedule=next_schedule, current=current, next=next)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password')
            return redirect(url_for('login'))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')

        if not next_page or url_parse(next_page).netloc != '':
            next_page= url_for('index')

        return redirect(next_page)

    return render_template('login.html', title='Log In', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = SignUpForm()
    message_template = "Hey Paul, someone named {} signed up for HangTime with the following info:\nPhone: {}\nEmail: {}\nInvite Code: {}\n\n-Luna"

    if form.validate_on_submit():
        if not app.config['ALLOW_SIGNUP']:
            flash('Sorry, you can\'t sign up at this time :( Reach out to us on the contact page to get added to the waitlist!')
            return redirect(url_for('signup'))

        user = User.query.filter_by(phone_number=form.phone_number.data).first()

        # in the future these both need to trigger verification first
        if user is not None:
            user.user_type = 'hang'
            user.first_name = form.first_name.data
            user.last_name = form.last_name.data
            user.set_password(form.password.data)
            user.email = form.email.data
            user.invite_code = form.invite_code.data
            db.session.commit()

            flash('Your account was claimed! Log in to start spending more time with friends')
        else:
            user = User(email=form.email.data, first_name=form.first_name.data, 
                        last_name=form.last_name.data, phone_number=form.phone_number.data, 
                        user_type='hang', invite_code=form.invite_code.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            flash('Your account was created! Log in to start spending more time with friends')

        message = message_template.format(form.first_name.data, form.phone_number.data, form.email.data, form.invite_code.data)
        messager.send(message, app.config['ADMIN_NUMBER'])
        return redirect(url_for('login'))

    return render_template('signup.html', title='Sign Up', form=form)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = EditProfileForm(current_user.email, current_user.phone_number)

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.fast_or_max = form.fast_or_max.data
        current_user.max_hang_per_week = form.max_hang_per_week.data
        current_user.updated_at = datetime.utcnow()
        db.session.commit()

        flash('Your changes have been saved.')

        return redirect(url_for('profile'))
    elif request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
        form.phone_number = current_user.phone_number
        form.max_hang_per_week.data = current_user.max_hang_per_week
        form.fast_or_max.data = current_user.fast_or_max


    return render_template('edit_profile.html', title='Edit Profile', form=form)

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = ResetPasswordRequestForm()

    if form.validate_on_submit():
        user = User.query.filter_by(phone_number=form.phone_number.data).first()
        if user and user.user_type == 'hang':
            token = user.get_reset_password_token()
            url = url_for('reset_password', token=token, _external=True)
            reset_password_msg = "Hi {}, to reset your password click on the following link:\n\n{}\n\nIf you have not requested a password reset simply ignore this message.\n-Luna".format(user.first_name, url)
            messager.send(reset_password_msg, user.phone_number)
            
        flash('Check your texts for instructions to reset your password!')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html',title='Reset Password', form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    user = User.verify_reset_password_token(token)

    if not user:
        return redirect(url_for('index'))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()

        flash('Your password has been reset.')
        
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/sms', methods=['GET', 'POST'])
def incoming_sms():
    resp = MessagingResponse()

    r_message = request.values.get('Body', None)
    r_sender = request.values.get('From', None)

    messager.handle_responses(r_sender, r_message)

    return 'OK!'

@app.route('/contact', methods=['GET','POST'])
def contact():
    # update to check if there is a logged in user in the future
    form = ContactForm()
    message_template = "Hi,\nSomeone named {} posted the following on the contact page:\n\n{}\n\nTheir email is {}\n -Luna"

    if form.validate_on_submit():
        name = form.name.data
        message = form.message.data
        email = form.email.data
        message = message_template.format(name, message, email)

        messager.send(message, app.config['ADMIN_NUMBER'])
        
        flash('Thanks for reaching out!')
        return redirect(url_for('login'))

    return render_template('contact.html', title='Contact', form=form)

@app.route('/about')
def about():
    return render_template('about.html', title='About')