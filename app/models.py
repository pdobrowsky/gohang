import jwt

from datetime import datetime
from app import db, login, app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from hashlib import md5
from time import time

# making a friends table up here like followers would make things better in some ways probably, and clean up logic here and in routes

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    phone_number = db.Column(db.String(255), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    user_type = db.Column(db.String(255), index=True, default='sms')
    max_hang_per_week = db.Column(db.Integer, default=3)
    password_hash = db.Column(db.String(128))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    friends = db.relationship('Friend', primaryjoin='user.c.id == friend.c.creator_user_id', lazy='dynamic')

    @login.user_loader
    def load_user(id):
        return User.query.get(int(id))

    def __repr__(self):
        return '<User {}>'.format(self.username)

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
    
    # def friend(self, user):
    #     if not self.is_friend(user):
    #         self.followed.append(user)

    def is_friend(self, user):
        return self.friends.filter_by(friend_user_id=user.id).count() > 0
    
    def unfriend(self, user):
        self.friends.remove(user)

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
    creator_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    friend_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    cadence = db.Column(db.Integer)
    provided_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, index=True)
    user = db.relationship('User', primaryjoin='user.c.id == friend.c.friend_user_id')

    def __repr__(self):
        return '<Friend creator_id: {} friend_id: {} cadence: {}weeks>'.format(self.creator_user_id, self.friend_user_id, self.cadence)
    
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, index=True)
    week_of = db.Column(db.DateTime, index=True)
    avails = db.Column(db.Text)
    processed_at = db.Column(db.DateTime, index=True)

    def __repr__(self):
        return '<Schedule user_id: {} created_at: {} avails: {} week of: {}>'.format(self.user_id, self.created_at, self.avails, self.week_of)
    
# need to start hangs model, handle coldstart