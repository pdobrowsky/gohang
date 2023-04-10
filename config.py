import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMINS = ['pdbrosky@gmail.com']
    ALLOW_SIGNUP = True
    TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_NUMBER = os.environ.get('TWILIO_NUMBER')
    ADMIN_NUMBER = os.environ.get('ADMIN_NUMBER')
    URL = os.environ.get('URL')
    INVITE_CODE = os.environ.get('INVITE_CODE')

    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')