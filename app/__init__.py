from flask import Flask, redirect, url_for
from instance.config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bootstrap import Bootstrap
from flask_login import LoginManager, current_user
from flask_admin import Admin, helpers, expose, AdminIndexView
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_jsglue import JSGlue
# from flask_mail import Mail
from flask_apscheduler import APScheduler
import sys, logging, os, logging.handlers, datetime
import atexit, time
from smtplib import SMTP
flask_app = Flask(__name__)

# V1.0 : initial version
# V1.1 : small update
# V1.2 : update in sending infomoment link e-mails
# V1.3 : small update, import e-mail addresses update
# V1.4 : increased page size to 200
# V1.5 : introduced logging.  Replaced flask_user with flask_login.  clean up
# V1.6 : show nbr of subscriptions for infomoment
# V1.7 : show double subscriptions for infomoment
# V1.8 : reworked sending emails
# V1.9 : udpate in db.app.app_context
# V1.10 : minor
# V1.11 : split settings and insight.  Check double booking when saving session
# V1.12 : protected change settings and added graceful shutdown
# V1.13 : introduced summernote to edit templates.  Add enable field to Invite
# V1.14 : bugfix activation of e-mail addresses
# V1.15 : minor update to get rid syntax errors in editor
# V1.16 : cleanup of app_context in send_emails_task.  Introduced timeslot_date to be able to sort on date
# V1.17 : db update is easier.  Added organization to have multiple surveys in parallel
# V1.18 : bugfix when uploading e-mailaddresses
# V1.19 : small bugfix
# V1.20 : small bugfix
# V1.21 : campussintursula.be may reserve mulitple timeslots.  Load sui emailaddresses
# V1.22 : handle exception when processing template
# V1.23 : flask-admin: added filter, adjusted CSS
# V1.24 : added sui insight
# V1.25 : small bugfix
# V1.26 : insight contactmoment : created a table
# V1.27 : added a view to get info without login
# V1.28 : contactmoment overview, add the number of available sessions
# V1.29 : scan multiple subrictions
# V1.30 : ack-e-mail has to link to unsubscribe for contactmoment and link to list all contactmoments
# V1.31 : when uploading e-mail addresses, take organization into account
# V1.32 : insight : add list of responses
# V1.33 : insight: add list of e-mailaddresses and a button to resend an invitation
# V1.34 : small bugfix
# V1.35 : insight : add button to subscribe per invite
# V1.36 : insight : add a button to add an invite
# V1.37 : insight : add button to remove a subsciption or invite
# V1.38 : insight : removed login-check
# V1.39 : insight : toggle activation of invite
# V1.40 : insight : take first and lastname into account when filtering for subscribed people
# V1.41 : insight : order invites on last name, first name
# V1.42 : save contactmoment bugfix : take organization into account
# V1.43 : insight : add button to update invite
# Vxlsx_support.V1.43.1 : add xlsx support, reworked insight
# Vxlsx_support.V1.43.2 : add TODO
# V1.44 : laptop pickup : implemented mails and pages
# V1.45 : ready to be deployed
# V1.46 : added ehlo
# V1.47 : added ehlo 2
# V1.48 : esthetic update
# V1.49 : esthetic update 2


# TODO : per student, one invite with 2 (3) e-mailaddresses
# TODO : invite : mail_sent : make it a counter
# TODO : invite : extra field for general information
# TODO : real username/password per organization

@flask_app.context_processor
def inject_version():
    return dict(version='V1.49')

# enable logging
LOG_HANDLE = 'SURVEY'
log = logging.getLogger(LOG_HANDLE)

LOG_FILENAME = os.path.join(sys.path[0], 'app/static/log/si-log.txt')
log_level = getattr(logging, 'INFO')
log.setLevel(log_level)
log_handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=10 * 1024, backupCount=5)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)
log.addHandler(log_handler)
log.info('start SURVEY')

flask_app.config.from_object(Config)
db = SQLAlchemy(flask_app)
migrate = Migrate(flask_app, db)
bootstrap = Bootstrap(flask_app)

# for login
login_manager = LoginManager(flask_app)
login_manager.login_message = 'Je moet aangemeld zijn om deze pagina te zien!'
login_manager.login_view = 'login'

jsglue = JSGlue(flask_app)

from app import models

mails = {}

if len(sys.argv) < 2 or len(sys.argv) > 1 and sys.argv[1] != 'db':
    # initialize db
    db.create_all()

    #initialize mail
    mail_server = flask_app.config['MAIL_SERVER']
    mail_port = flask_app.config['MAIL_PORT']
    for email_account in flask_app.config['MAIL_ACCOUNTS']:
        flask_app.config['MAIL_USERNAME'] = email_account['username']
        flask_app.config['MAIL_PASSWORD'] = email_account['password']

        host = SMTP(host=mail_server, port=mail_port)
        host.ehlo()
        host.starttls()
        host.ehlo()
        host.login(email_account['username'], email_account['password'])
        mails[email_account['username']] = host
    send_emails = False

    SCHEDULER_API_ENABLED = True
    scheduler = APScheduler()
    scheduler.init_app(flask_app)
    scheduler.start()

    if not models.Role.query.filter_by(name="Admin").first():
        role_admin = models.Role(name='Admin')
        db.session.add(role_admin)
        db.session.commit()
    if not models.Role.query.filter_by(name="User").first():
        role_user = models.Role(name='User')
        db.session.add(role_user)
        db.session.commit()
    if not models.User.query.filter_by(password=flask_app.config['ADMIN_TOKEN']).first():
        role_ = models.Role.query.filter_by(name="Admin").first()
        admin_user = models.User(password=flask_app.config['ADMIN_TOKEN'], used=False)
        admin_user.roles = [role_,]
        db.session.add(admin_user)
        db.session.commit()

    models.update_links()
    models.update_email_tokens()

    from app import routes

    from .laptop_pickup import laptop_pickup as laptop_pickup_blueprint
    flask_app.register_blueprint(laptop_pickup_blueprint)

    class MyAdminIndexView(AdminIndexView):
        @expose('/')
        def index(self):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            return super(MyAdminIndexView, self).index()

    admin = Admin(flask_app, name='Backend', index_view=MyAdminIndexView(), template_mode='bootstrap3')


    class BaseModelView(ModelView):
        def is_accessible(self):
            if not current_user.is_authenticated: return False
            return current_user.has_roles('Admin')

        can_export = True
        page_size = 200


    class MyModelView(BaseModelView):
        def after_model_change(self, form, model, is_created):
            if type(model) == models.Timeslot or type(model) == models.Topic:
                models.update_links()
            if type(model) == models.Invite:
                models.update_email_tokens()

        def after_model_delete(self, model):
            if type(model) == models.Timeslot or type(model) == models.Topic:
                models.update_links()
            if type(model) == models.Invite:
                models.update_email_tokens()

    admin.add_view(MyModelView(models.Setting, db.session))
    admin.add_view(MyModelView(models.ContactTimeslot, db.session, category='Contactmoment'))

    class ContactResponseView(BaseModelView):
        column_list = ['organization', 'timeslot_date', 'timeslot', 'invite.first_name', 'invite.last_name', 'invite.email', 'email_sent']
        column_filters = ['organization']

    admin.add_view(ContactResponseView(models.ContactResponse, db.session, category='Contactmoment'))

    # admin.add_link(MenuLink(name='Insight', category='SUI-contact', url='\info\SUI\internal'))
    # admin.add_link(MenuLink(name='settings', category='SUI-contact', url='\settings\SUI'))
    # admin.add_link(MenuLink(name='Multiple', category='SUI-contact', url='\multiple_subscriptions\SUI'))
    admin.add_link(MenuLink(name='Settings', category='SUM-laptop', url='/settings/SUMLPU'))
    admin.add_link(MenuLink(name='Insight', category='SUM-laptop', url='/info/SUMLPU/internal'))
    admin.add_link(MenuLink(name='Uitloggen', category='', url='\logout'))


    def close_app():
        log.info('Graceful shut down')
        routes.stop_send_email_task()
        scheduler.shutdown()
        log.info('Bye...')

    atexit.register(close_app)

    models.Setting.default_init()
    models.ContactResponse.default_init()