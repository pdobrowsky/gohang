from flask import render_template, flash, redirect, request, url_for
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db
from app.forms import LoginForm, SignUpForm, EditProfileForm, ResetPasswordRequestForm, ResetPasswordForm, EmptyForm, FriendForm
from app.models import User, Friend
from app.emails import send_password_reset_email
from datetime import datetime

def add_friend(form):
    user = User.query.filter_by(phone_number=form.phone_number.data).first()

    if user is None:
        user = User(phone_number=form.phone_number.data, first_name=form.name.data)
        db.session.add(user)
        db.session.commit()
        user = User.query.filter_by(phone_number=form.phone_number.data).first()
    elif user == current_user: 
        flash('You can\'t friend yourself!')
    elif current_user.is_friend(user):
        flash('You\'ve already added {} as a friend!'.format(form.name.data))

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

    if form.validate_on_submit():
        add_friend(form)
        return redirect(url_for('index'))

    return render_template('index.html', title='Home', form=form)

@app.route('/friends', methods=['GET','POST'])
@login_required
def friends():
    form = FriendForm()
    friends = Friend.query.filter_by(creator_user_id=current_user.id)

    if form.validate_on_submit():
        add_friend(form)
        return redirect(url_for('friends'))

    return render_template('friends.html', title='Friends', form=form, friends=friends)

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

@app.route('/schedule', methods=['GET'])
@login_required
def schedule():
    return render_template('schedule.html', title='Schedule')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
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

    if form.validate_on_submit():
        if app.config['ALLOW_SIGNUP']:
            user = User(username=form.username.data, email=form.email.data, first_name=form.first_name.data, 
                        last_name=form.last_name.data, phone_number=form.phone_number.data, user_type='hang')
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            flash('Your account was created! Log in to start spending more time with friends')
            return redirect(url_for('login'))
        else:
            flash('Sorry, you can\'t sign up at this time :( Waitlist coming soon!')
            return redirect(url_for('index'))

    return render_template('signup.html', title='Sign Up', form=form)

@app.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()

    form= EmptyForm()
    return render_template('user.html', user=user, form=form)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username, current_user.email, current_user.phone_number)

    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.email = form.email.data
        current_user.phone_number = form.phone_number.data
        db.session.commit()

        flash('Your changes have been saved.')

        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
        form.phone_number = current_user.phone_number

    return render_template('edit_profile.html', title='Edit Profile', form=form)

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html',
                           title='Reset Password', form=form)

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