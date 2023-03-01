from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from wtforms.fields import DateField
from app.models import User
from datetime import datetime

import phonenumbers
import collections

def check_phone_number(phone_number):
    try:
        p = phonenumbers.parse(phone_number.data)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        raise ValidationError('Invalid phone number.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')

class SignUpForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=30)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=30)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    phone_number = StringField('Phone Number', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()

        if user is not None:
            raise ValidationError('This username is already taken.')

    def validate_email(self, email):
        email = User.query.filter_by(email=email.data).first()

        if email is not None:
            raise ValidationError('This email is already associated with an account.')
        
    def validate_phone_number(self, phone_number):
        check_phone_number(phone_number)

        user = User.query.filter_by(phone_number=phone_number.data).first()

        if user is not None:
            raise ValidationError('This username is already taken.')

class EditProfileForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=30)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=30)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    phone_number = StringField('Phone Number', validators=[DataRequired(),])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField('Submit')

    def __init__(self, original_username, original_email, original_phone_number, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email
        self.original_phone_number = original_phone_number

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('This username is already taken.')
            
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(username=self.email.data).first()
            if user is not None:
                raise ValidationError('This email is already taken.')
        
    def validate_phone_number(self, phone_number):
        check_phone_number(phone_number)
        
        if phone_number.data != self.phone_number:
            user = User.query.filter_by(username=self.phone_number.data).first()
            if user is not None:
                raise ValidationError('This number is already taken.')

class ResetPasswordRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Request Password Reset')

class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')

class FriendForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=30)])
    phone_number = StringField('Phone Number', validators=[DataRequired()])
    cadence = SelectField('Try to hang ever X weeks:', choices=[1,2,3,4,5,6,7,8], validators=[DataRequired()], default=3)
    submit = SubmitField('Add Friend')

    def validate_phone_number(self, phone_number):
        check_phone_number(phone_number)

class ScheduleForm(FlaskForm):
    submit = SubmitField('Submit')
    dt = DateField('DatePicker', format='%Y-%m-%d', validators=[DataRequired()])

    def validate_dt(self, dt):
        if datetime.utcnow().date().isocalendar().week > dt.data.isocalendar().week:
            raise ValidationError("That week is in the past")

for time in ['Morning', 'Afternoon', 'Evening']:
    for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
        setattr(ScheduleForm, time + day, BooleanField() ) 