from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from wtforms.fields import DateField
from app.models import User
from app import app
from datetime import datetime

import phonenumbers

def check_phone_number(phone_number):
    try:
        p = phonenumbers.parse(phone_number.data)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        raise ValidationError('Invalid phone number.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')

class SignUpForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=30)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=30)])
    phone_number = StringField('Phone Number', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    invite_code = StringField('Invite Code', validators=[Length(max=30)])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        email = User.query.filter_by(email=email.data, user_type='hang').first()

        if email is not None:
            raise ValidationError('This email is already associated with an account.')
        
    def validate_phone_number(self, phone_number):
        check_phone_number(phone_number)

        user = User.query.filter_by(phone_number=phone_number.data, user_type='hang').first()

        if user is not None:
            raise ValidationError('This phone number is already taken.')
        
    def validate_invite_code(self, invite_code):
        if invite_code.data != app.config['INVITE_CODE']:
            raise ValidationError('Invalid invite code.')

class EditProfileForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=30)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=30)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)], render_kw={'readonly': True})
    max_hang_per_week = SelectField('Max Hangs Per Week', choices=[1,2,3,4], coerce=int, validators=[DataRequired()])
    fast_or_max = SelectField('Fast or Max', choices=[('fast', 'Fast'), ('max', 'Max')], validators=[DataRequired()])
    submit = SubmitField('Submit')

    def __init__(self, original_email, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
            
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=self.email.data).first()
            if user is not None:
                raise ValidationError('This email is already taken.')
            
class EditFriendForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=30)])
    cadence = SelectField('Try to hang ever X weeks:', choices=[1,2,3,4,5,6,7,8], coerce=int, validators=[DataRequired()])
    submit = SubmitField('Edit Friend')

class ResetPasswordRequestForm(FlaskForm):
    phone_number = StringField('Phone Number', validators=[DataRequired()])
    submit = SubmitField('Request Password Reset')

    def validate_phone_number(self, phone_number):
        check_phone_number(phone_number)

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

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=30)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    message = TextAreaField(validators=[DataRequired(), Length(min=1, max=280)])
    submit = SubmitField('Submit')

class ScheduleForm(FlaskForm):
    submit = SubmitField('Submit')
    week = StringField('Week', validators=[DataRequired()])

    def validate_dt(self, week):
        if datetime.utcnow().date().isocalendar().week > int(week.data[-2:]):
            raise ValidationError("That week is in the past")

for time in ['Morning', 'Afternoon', 'Evening']:
    for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']:
        setattr(ScheduleForm, time + day, BooleanField() ) 