from app import db, login_manager
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
from flask_login import UserMixin
import hashlib, datetime

class Topic(db.Model):
    __tablename__ = 'topics'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(256))
    info = db.Column(db.String(1024))
    responses = db.relationship('Response', cascade='all', backref='topic', lazy='dynamic')
    links = db.relationship('Link', cascade='all', backref='topic', lazy='dynamic')


class Timeslot(db.Model):
    __tablename__ = 'timeslots'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(256))
    responses = db.relationship('Response', cascade='all', backref='timeslot', lazy='dynamic')
    links = db.relationship('Link', cascade='all', backref='timeslot', lazy='dynamic')


class Response(db.Model):
    __tablename__ = 'responses'
    id = db.Column(db.Integer(), primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())
    email_sent = db.Column(db.Boolean, default=False)
    invite_id = db.Column(db.Integer, db.ForeignKey('invites.id'))
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'))
    timeslot_id = db.Column(db.Integer, db.ForeignKey('timeslots.id'))


class Link(db.Model):
    __tablename__ = 'links'
    id = db.Column(db.Integer(), primary_key=True)
    active = db.Column(db.Boolean, default=True)
    enabled = db.Column(db.Boolean, default=True)
    link = db.Column(db.String(4096))
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'))
    timeslot_id = db.Column(db.Integer, db.ForeignKey('timeslots.id'))


def update_links():
    topics = Topic.query.all()
    timeslots = Timeslot.query.all()

    links = Link.query.filter().all()
    for link in links:
        link.active = False

    for timeslot in timeslots:
        for topic in topics:
            link = Link.query.filter(Link.topic==topic, Link.timeslot==timeslot).first()
            if link:
                if link.enabled:
                    link.active = True
            else:
                link = Link(topic=topic, timeslot=timeslot, active=True)
                db.session.add(link)
    db.session.commit()


class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer(), primary_key=True)
    key = db.Column(db.String(256))
    value = db.Column(db.String(16384))

    update_keys = {
        'keep' : [
            '_send_invite_contactmoment_email',
            '_send_ack_contactmoment_email',
            '_template_invite_contactmoment',
            '_template_ack_contactmoment',
        ],
        'change' : [
            ['sui', 'SUI'],
            ['sum_lpu', 'SUMLPU'],
        ]
    }
    @staticmethod
    def default_init():
        key =  Setting.update_keys['change'][1][1] + Setting.update_keys['keep'][0]
        setting = Setting.query.filter(Setting.key == key).first()
        if setting: return
        for c in Setting.update_keys['change']:
            for k in Setting.update_keys['keep']:
                setting = Setting.query.filter(Setting.key == (c[0] + k)).first()
                setting.key = c[1] + k
        db.session.commit()
        


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)

class UserRoles(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('token.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('roles.id', ondelete='CASCADE'))

class User(UserMixin, db.Model):
    __tablename__ = 'token'
    id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(64), index=True, unique=True)
    used = db.Column(db.Boolean)

    roles = db.relationship('Role', secondary='user_roles')

    def is_Admin(self):
        if 'Admin' in self.roles:
            return True
        else: return False

    def has_roles(self, *args):
        return set(args).issubset({role.name for role in self.roles})

    def __repr__(self):
        return '<Token {}>'.format(self.password)

def update_email_tokens():
    invites = Invite.query.filter(Invite.token == None).all()
    for invite in invites:
        token = hashlib.md5(invite.email.encode())
        invite.token = token.hexdigest()
    db.session.commit()


class Invite(db.Model):
    __tablename__ = 'invites'

    id = db.Column(db.Integer(), primary_key=True)
    active = db.Column(db.Boolean, default=True)
    enable = db.Column(db.Boolean, default=True)
    email = db.Column(db.String(256))
    first_name = db.Column(db.String(256))
    last_name = db.Column(db.String(256))
    class_group = db.Column(db.String(256), default='')
    token = db.Column(db.String(256))
    infomoment_sent = db.Column(db.Boolean, default=False)
    contactmoment_sent = db.Column(db.Boolean, default=False)
    contact_responses = db.relationship('ContactResponse', cascade='all', backref='invite')
    responses = db.relationship('Response', cascade='all', backref='invite')
    organization = db.Column(db.String(256))


class ContactTimeslot(db.Model):
    __tablename__ = 'contact_timeslots'

    id = db.Column(db.Integer(), primary_key=True)
    active = db.Column(db.Boolean, default=False)
    nbr_sessions = db.Column(db.Integer())
    date = db.Column(db.String(256))
    first = db.Column(db.Integer())
    last = db.Column(db.Integer())
    length = db.Column(db.Integer())
    break_start = db.Column(db.Integer())
    break_length = db.Column(db.Integer())
    buffer_every = db.Column(db.Integer())
    buffer_length = db.Column(db.Integer())
    organization = db.Column(db.String(256))


class ContactResponse(db.Model):
    __tablename__ = 'contact_responses'

    id = db.Column(db.Integer(), primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())
    invite_id = db.Column(db.Integer, db.ForeignKey('invites.id'))
    timeslot = db.Column(db.String(256))
    email_sent = db.Column(db.Boolean, default=False)
    timeslot_date = db.Column(db.DateTime(timezone=True))
    info = db.Column(db.String(256), default='')
    organization = db.Column(db.String(256))

    @staticmethod
    def default_init():
        response = ContactResponse.query.filter(ContactResponse.info == None).first()
        if response:
            responses = ContactResponse.query.all()
            for response in responses:
                response.info = ''
            db.session.commit()
