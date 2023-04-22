import jwt
import pandas as pd

from datetime import datetime
from app import db, login, app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from hashlib import md5
from time import time
from sqlalchemy import or_, and_

# !!!!need to update week of logic to account for year changeover in future

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    phone_number = db.Column(db.String(255), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    user_type = db.Column(db.String(255), index=True, default='sms')
    max_hang_per_week = db.Column(db.Integer, default=3)
    fast_or_max = db.Column(db.String(255), default='fast')
    password_hash = db.Column(db.String(128))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)
    friends = db.relationship('Friend', primaryjoin='user.c.id == friend.c.creator_user_id', lazy='dynamic')

    @login.user_loader
    def load_user(id):
        return User.query.get(int(id))

    def __repr__(self):
        return '<User {}>'.format(self.email)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in}, 
            app.config['SECRET_KEY'], 
            algorithm='HS256')

    def is_friend(self, user):
        return self.friends.filter_by(friend_user_id=user.id).count() > 0
    
    def unfriend(self, user):
        self.friends.remove(user)

    def upcoming_hangs(self, week_of):
        hangs = db.session.query(Hang, User, Friend.provided_name)\
            .filter(or_(Hang.user_id_1==self.id, Hang.user_id_2==self.id), Hang.week_of==week_of)\
            .join(User, or_(User.id == Hang.user_id_1, User.id == Hang.user_id_2))\
            .filter(User.id != self.id)\
            .join(Friend, or_(and_(Friend.creator_user_id == self.id, Friend.friend_user_id == User.id), and_(Friend.creator_user_id == User.id, Friend.friend_user_id == self.id)))\
            .order_by(Hang.updated_at.desc())

        return hangs
    
    def non_mutual_friends(self):
        # checks what hang users have friended you that you haven't friended to make them easy to add as mutuals
        # ignores whether the other user is still a hang user
        friended_by = db.session.query(Friend).filter(Friend.friend_user_id==self.id).all()
        not_friended = []

        for friend in friended_by:
            u = User.query.get(friend.creator_user_id)
            if not self.is_friend(u):
                not_friended.append(u)

        return not_friended

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)
    
class Friend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    friend_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    cadence = db.Column(db.Integer)
    provided_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, index=True)
    user = db.relationship('User', primaryjoin='user.c.id == friend.c.friend_user_id')

    def __repr__(self):
        return '<Friend creator_id: {} friend_id: {} cadence: {}weeks>'.format(self.creator_user_id, self.friend_user_id, self.cadence)
    
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, index=True)
    week_of_int = db.Column(db.Integer, index=True)
    avails = db.Column(db.Text)

    def __repr__(self):
        return '<Schedule user_id: {} created_at: {} avails: {} week of: {}>'.format(self.user_id, self.created_at, self.avails, self.week_of)
    
class Hang(db.Model):
    # need friend ID?
    id = db.Column(db.Integer, primary_key=True)
    user_id_1 = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    user_id_2 = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, index=True)
    schedule = db.Column(db.Text)
    week_of = db.Column(db.Integer, index=True)
    state = db.Column(db.String(255), index=True)
    priority = db.Column(db.Float(), index=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id')) # ghost field, not used but annyoing to remove because of fk constraint, not sure what name is
    reminded = db.Column(db.Boolean, index=True, default=False)
    finalized_slot = db.Column(db.String(255))
    retry = db.Column(db.Boolean, index=True, default=False)
    reminded = db.Column(db.Boolean, index=True, default=False)
    friend_type = db.Column(db.String(255), index=True)

    def __repr__(self):
        return '<Hang>'