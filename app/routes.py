from flask import render_template, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app.forms import LoginForm
from app import flask_app,  db, log, scheduler, mail
from flask_login import login_user, logout_user
from app.models import Setting, User, Link, Invite, ContactTimeslot, ContactResponse, update_email_tokens
import datetime, time, sys, re
from flask_mail import Message
import json, random
import pandas as pd

import flask_excel as excel


@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/admin')
    form = LoginForm()
    if form.validate_on_submit():
        token = User.query.filter_by(password = form.accessToken.data, used=False).first()
        if token is None:
            flash('Geen geldig token of token reeds gebruikt.')
            return redirect(url_for('login'))
        login_user(token)
        return redirect('/admin')
    return render_template('login.html', title='Inloggen', form=form)


@flask_app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

def insight_decode_time(slot, type, time, h, m, delta):
    time_str = str(time)
    decoded_time = time_str[:-2] + '.' + time_str[-2:]
    slot.append({'count': 0, 'time': decoded_time})
    m += delta
    if m >= 60:
        m -= 60
        h += 1
    i = h * 100 + m
    return i, h, m, decoded_time


@flask_app.route('/info_inschrijvingen/<string:org>/<string:token>', methods=['GET', 'POST'])
def info_subscriptions(org, token):
    invite = Invite.query.filter(Invite.token == token, Invite.organization == org).first()
    if not invite:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=org,
                               email_token='', error='no_invite')
    responses = ContactResponse.query.filter(ContactResponse.invite == invite).all()
    info = [response.timeslot.replace('-', ' om ') for response in responses]
    return render_template('info_subscriptions.html', title='Inschrijvingen', info=info, organization=org,
                           email=invite.email)


@flask_app.route('/info/<string:org>/<string:token>/<string:topic>', methods=['GET', 'POST'])
@flask_app.route('/info/<string:org>/<string:token>', methods=['GET', 'POST'])
def info(org, token, topic=None):
    if token == flask_app.config['INFO_TOKEN'] or token == 'internal' and current_user.is_authenticated:
        if topic == 'backend':
            return redirect('/admin')
        topic = topic if topic else 'subscriptions'
        return get_insight(org, token, topic)
    return 'Error 404: fuck off'


@flask_app.route('/insight/<string:org>', methods=['GET', 'POST'])
# @login_required
def insight(org):
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return get_insight(org, 'intern', 'invites')


def get_insight(org, info_token = None, topic='subscriptions'):
    infomoment_info = []
    contact_table = []
    responses_count = 0
    invites_info =[]
    invites_count= 0
    navbar_title = ''
    responses = ContactResponse.query.filter(ContactResponse.organization == org).order_by(
        ContactResponse.timeslot_date).all()

    if topic == 'subscriptions':
        contact_table, timeslot_length = create_contactmoment_table(org, insight_decode_time)
        for day in contact_table:
            date = day['date']
            timeslot = ContactTimeslot.query.filter(ContactTimeslot.date == date, ContactTimeslot.organization == org).first()
            for slot in day['slots']:
                key = date + '-' + slot['time']
                contact_response_count = ContactResponse.query.filter(ContactResponse.organization == org,
                                                                      ContactResponse.timeslot == key).count()
                slot['count'] = contact_response_count
            day['date'] += f' ({timeslot.nbr_sessions})' if timeslot else ' (0)'

        responses_count = len(responses)
        navbar_title = f'Overzicht inschrijvingen van {org}'

    nsubscribed = 0
    not_subscribed_cache = set()
    if topic == 'invites':
        invites = Invite.query.filter(Invite.organization == org, Invite.enable == True).\
            order_by(Invite.last_name, Invite.first_name).all()
        base_url = Setting.query.filter(Setting.key == 'base_url').first().value
        response_invit_first_last_name = [f'{r.invite.first_name}{r.invite.last_name}' for r in responses]
        invites_info = []
        for i in invites:
            subscribed = f'{i.first_name}{i.last_name}' in response_invit_first_last_name
            if subscribed:
                nsubscribed += 1
            else:
                not_subscribed_cache.add(f'{i.first_name}{i.last_name}')
            invites_info.append({
                'email': i.email,
                'first_name': i.first_name,
                'last_name': i.last_name,
                'url': base_url + '/subscribe/' + org + '/' + i.token,
                'id': i.id,
                'active': i.active,
                'subscribed': subscribed,
            })
        invites_count = len(invites)
        navbar_title = f'Overzicht e-mailaddressen van {org}'


    info = {
        'infomoment_info': infomoment_info,
        'contact_table': contact_table,
        'organization': org,
        'responses': responses,
        'responses_count': responses_count,
        'invites': invites_info,
        'invites_count': invites_count,
        'nsubscribed': nsubscribed,
        'nnotsubscribed': len(not_subscribed_cache),
        'nstudents': nsubscribed + len(not_subscribed_cache),
    }

    return render_template('insight.html', title='Overzicht', info=info, info_token=info_token, topic = topic,
                           navbar_title=navbar_title)


@flask_app.route('/multiple_subscriptions/<string:org>', methods=['GET', 'POST'])
@login_required
def multiple_subscriptions(org):
    contact_responses = ContactResponse.query.filter(ContactResponse.organization == org).all()
    multiple = {}
    for response in contact_responses:
        if response.invite.email in multiple: continue
        multiple_found = ContactResponse.query.filter(ContactResponse.organization == org).join(Invite).\
            filter(Invite.email == response.invite.email).all()
        if len(multiple_found) > 1:
            multiple[response.invite.email] = [r.timeslot for r in multiple_found]
    return render_template('multiple.html', title='Dubbele inschrijvingen', info = multiple)


def extract_subject_and_content(template):
    try:
        subject_pattern = 'TAG_ONDERWERP_START.*\[\((.*?)\)\].*TAG_ONDERWERP_STOP'
        subject1 = re.search(subject_pattern, template).group(1)
        subject_pattern = 'TAG_ONDERWERP2_START.*\[\((.*?)\)\].*TAG_ONDERWERP2_STOP'
        subject2 = re.search(subject_pattern, template)
        if subject2:
            subject2 = subject2.group(1)
        content_pattern = 'TAG_INHOUD_START.*\[\((.*?)\)\].*TAG_INHOUD_STOP'
        content1 = re.search(content_pattern, template).group(1)
        content_pattern = 'TAG_INHOUD2_START.*\[\((.*?)\)\].*TAG_INHOUD2_STOP'
        content2 = re.search(content_pattern, template)
        if content2:
            content2 = content2.group(1)
        return subject1, subject2, content1, content2
    except Exception as e:
        log.error(f'extract_subject_and_content: {e}')


#Compose the email that is send with a link to subscribe for a contactmoment session
def send_email_with_link_to_subscribe_for_contactmoment(**kwargs):
    ret = False
    if 'org' in kwargs:
        organization = kwargs['org']
        invite_template_key = '_'.join([organization, 'template_invite_contactmoment'])
        enable_invite_key = '_'.join([organization, 'send_invite_contactmoment_email'])
        if not int(Setting.query.filter(Setting.key == enable_invite_key).first().value): return False
        invite = Invite.query.filter(Invite.active == True, Invite.enable == True,
                                     Invite.organization == organization, Invite.contactmoment_sent == False).first()
        if not invite: return False
        template = Setting.query.filter(Setting.key == invite_template_key).first().value
        email_subject, _, email_body, _ = extract_subject_and_content(template)
        base_url = Setting.query.filter(Setting.key == 'base_url').first().value
        link = base_url + '/' + 'subscribe' + '/' + organization + '/' + invite.token
        email_info = {
            'body': email_body.replace('TAG_LINK_URL', link),
            'subject': email_subject,
            'to': invite.email,
        }
        log.info(f'"{email_subject}" to {invite.email}')
        ret = send_email(organization, email_info)
        if ret:
            invite.contactmoment_sent = True
            db.session.commit()
    return ret


#Compose the email that is send with acknowledgement of a contactmoment
def send_email_with_ack_of_contactmoment(**kwargs):
    ret = False
    if 'org' in kwargs:
        organization = kwargs['org']
        ack_template_key = '_'.join([organization, 'template_ack_contactmoment'])
        enable_ack_key = '_'.join([organization, 'send_ack_contactmoment_email'])
        if not int(Setting.query.filter(Setting.key == enable_ack_key).first().value): return False
        response = ContactResponse.query.filter(ContactResponse.email_sent == False,
                                                ContactResponse.organization == organization).first()
        if response:
            template = Setting.query.filter(Setting.key == ack_template_key).first().value
            if organization == 'SUMLPU':
                subject_student, subject_parent, body_student, body_parent = extract_subject_and_content(template)
                if response.info == 'student':
                    email_body = body_student
                    email_subject = subject_student
                else:
                    timeslot = response.timeslot.replace('-', ' om ')
                    email_body = body_parent.replace('TAG_CONTACTMOMENT', timeslot)
                    email_subject = subject_parent
                base_url = Setting.query.filter(Setting.key == 'base_url').first().value
                link = base_url + '/' + 'subscribe' + '/' + organization + '/' + response.invite.token
                email_info = {
                    'body': email_body.replace('TAG_LINK_URL', link),
                    'subject': email_subject,
                    'bcc_list': [],
                    'to': response.invite.email,
                }
                log.info(f'"{email_subject}" to {response.invite.email}')
                ret = send_email(organization, email_info)
                if ret:
                    response.email_sent = True
                    db.session.commit()
    return ret


def store_email_address(email, first_name, last_name, organization, class_group):
    if '@' in email:
        invite = Invite.query.filter(Invite.email == email, Invite.organization == organization).first()
        if invite:
            invite.class_group = class_group
        else:
            invite = Invite(email=email, first_name=first_name, last_name=last_name, organization=organization,
                            class_group=class_group)
            db.session.add(invite)
            return True
    return False

org_to_upload_email_info = {
    'SUI': {
        'first_name': 'sui_upload_email_first_name',
        'last_name': 'sui_upload_email_last_name',
        'email_1': 'sui_upload_email_address_1',
        'email_2': 'sui_upload_email_address_2',
        'organization': 'sui_upload_email_organization',
    },
    'SUMLPU': {
        'first_name': 'sui_upload_email_first_name',
        'last_name': 'sui_upload_email_last_name',
        'email_1': 'sui_upload_email_address_1',
        'email_2': 'sui_upload_email_address_2',
        'organization': 'sui_upload_email_organization',
    },
}

@flask_app.route('/load_email_addresses', methods=['GET', 'POST'])
@login_required
def load_email_addresses():
    if True:
    # if 'upload_email_addresses' in request.files:
        organization = request.values['organization']
        nbr_entries = 0
        nbr_email_addresses = 0
        raw_emails_file_storage = request.files['upload_email_addresses']
        info = org_to_upload_email_info[organization]
        first_name_field = 'Voornaam'
        last_name_field = 'Naam'
        email_1_field = 'LL_MOEDEREMAIL'
        email_2_field = 'LL_VADEREMAIL'
        organization_field = 'Deelschool'
        class_field = 'Klas'
        try:
            emails_dict = pd.read_excel(raw_emails_file_storage, sheet_name='Form1',
                                        usecols=[first_name_field, last_name_field, organization_field, class_field,
                                                 email_1_field, email_2_field]).fillna('').to_dict(orient='records')
            for entry in emails_dict:
                if (organization_field != '' and entry[organization_field].upper() == organization) or organization_field == '':
                    ok1 = store_email_address(entry[email_1_field], entry[first_name_field], entry[last_name_field],
                                              organization, entry[class_field])
                    nbr_email_addresses += 1 if ok1 else 0
                    ok2 = store_email_address(entry[email_2_field], entry[first_name_field], entry[last_name_field],
                                              organization, entry[class_field])
                    nbr_email_addresses += 1 if ok2 else 0
                    nbr_entries += 1 if ok1 or ok2 else 0
            db.session.commit()
            update_email_tokens()
            flash(f'E-mailaddressen zijn opgeladen:<br>{nbr_entries} leerlingen<br>{nbr_email_addresses} e-mailadressen')
        except Exception as e:
            flash(f'Er is een fout opgetreden: {e}')
    else:
        flash('Sorry, dit is geen goed bestand')
    return redirect(url_for('settings', organization=organization))


@flask_app.route('/export_invites', methods=['GET', 'POST'])
def export_invites():
    invites = Invite.query.filter(Invite.organization == 'SUMLPU').all()
    data = [['status', 'datum', 'voonaam', 'naam', 'klas']]
    data_cache = {}
    for invite in invites:
        state = 'geen antwoord'
        date = 'nvt'
        class_group = invite.class_group if invite.class_group else ''
        if invite.contact_responses:
            response = invite.contact_responses[0]
            if response.info == 'student':
                state = 'student'
            else:
                state = 'tijdslot'
                date = response.timeslot
        key = invite.first_name + invite.last_name + class_group
        if not key in data_cache:
            data_cache[key] = [state, date, invite.first_name, invite.last_name, class_group]
        else:
            if state != 'geen antwoord':
                data_cache[key][0] = state
                data_cache[key][1] = date
    for k, v in data_cache.items():
        data.append(v)
    return excel.make_response_from_array(data, "xlsx", file_name=u"overzicht-laptop-afhalen.xlsx")


def create_contactmoment_table(organization, decode_time_cb):
    contact_moments = ContactTimeslot.query.filter(ContactTimeslot.active == True,
                                                   ContactTimeslot.organization == organization).all()
    contact_table = []
    timeslot_length = contact_moments[0].length if contact_moments else 0
    for moment in contact_moments:
        slots = []
        buffer = 0
        h = int(moment.first / 100)
        m = moment.first - h * 100

        i = moment.first
        i = h * 100 + m
        while i < moment.last:
            if moment.buffer_every > 0 and buffer >= moment.buffer_every and \
                    not (moment.break_start <= i <= (moment.break_start + moment.break_length)):
                i, h, m, slot = decode_time_cb(slots, 'buffer', i, h, m, moment.buffer_length)
                buffer = 0
            if moment.break_start > 0 and (moment.break_start + moment.break_length) > i >= moment.break_start:
                i, h, m, slot = decode_time_cb(slots, 'break', i, h, m, moment.break_length)
                buffer = 0
            buffer += moment.length
            i, h, m, slot = decode_time_cb(slots, 'free', i, h, m, moment.length)
            id = moment.date + '-' + slot
            nbr_subscriptions = ContactResponse.query.filter(ContactResponse.timeslot == id,
                                                             ContactResponse.organization == organization).count()
            if nbr_subscriptions >= moment.nbr_sessions:
                slots[-1]['type'] = 'busy'
        item = {
            'date': moment.date,
            'slots': slots
        }
        contact_table.append(item)
    return contact_table, timeslot_length


def decode_time(slot, type, time, h, m, delta):
    time_str = str(time)
    decoded_time = time_str[:-2] + '.' + time_str[-2:]
    slot.append({'type': type, 'time': decoded_time})
    m += delta
    if m >= 60:
        m -= 60
        h += 1
    i = h * 100 + m
    return i, h, m, decoded_time

@flask_app.route('/subscribe/SUI/<string:token>', methods=['GET', 'POST'])
def subscribe_contactmoment(organization=None, token=None):
    contact_table, timeslot_length = create_contactmoment_table(organization, decode_time)
    email = ''
    if token or token != 'None':
        invite = Invite.query.filter(Invite.token == token, Invite.organization == organization).first()
        if invite:
            email = invite.email

    return render_template('subscribe_contactmoment.html', title='Inschrijven', contact_table=contact_table,
                           email_token=token, email=email, organization=organization, timeslot_length=timeslot_length)


@flask_app.route('/uitschrijven_contactmoment', methods=['GET', 'POST'])
@flask_app.route('/uitschrijven_contactmoment/<string:organization>/<string:timeslot>/<string:token>', methods=['GET', 'POST'])
def unsubscribe_contactmoment(organization=None, timeslot=None, token=None):
    timeslot = timeslot.replace('@', '/')
    response = ContactResponse.query.filter(ContactResponse.organization == organization, ContactResponse.timeslot == timeslot).\
        join(Invite).filter(Invite.token == token).first()
    if not response:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=organization,
                               email_token='', error='booking_not_found')
    email_token = response.invite.token
    contactmoment = response.timeslot.replace('-', ' om ')
    return render_template('unsubscribe_subscription.html', title='Uitschrijven', contactmoment=contactmoment,
                           id=response.id, email_token=email_token, organization=organization)


@flask_app.route('/uitschrijven_contactmoment_bevestig/<string:organization>/<string:token>/<int:id>', methods=['GET', 'POST'])
def unsubscribe_contactmoment_confirm(organization, token, id):
    invite = Invite.query.filter(Invite.token == token, Invite.organization == organization).first()
    if invite:
        response = ContactResponse.query.get(id)
        if response and response.invite == invite:
            contactmoment = response.timeslot.replace('-', ' om ')
            db.session.delete(response)
            db.session.commit()
            return render_template('success_contactmoment.html', title='Bedankt', email='', contactmoment=contactmoment,
                                       organization=invite.organization, email_token='', info='unsubscribed')
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=organization,
                               email_token='', error='booking_not_found')


@flask_app.route('/save_contactmoment', methods=['POST'])
def save_contactmoment():
    email = request.form['email']
    organization = request.form['organization']
    email_token = request.form['email_token'] if 'email_token' in request.form else None
    invite = Invite.query.filter(Invite.email == email, Invite.organization == organization).first()
    if not invite:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=organization,
                               email_token=email_token, error='no_invite')
    if not 'chbx' in request.form:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=organization,
                               email_token=email_token, error='nothing_selected')
    timeslot = request.form['chbx']
    email_from_suc = email.split('@')[-1].lower() == 'campussintursula.be'
    ida = timeslot.split('-')
    date = ida[0]
    time = ida[1]
    contactmoment = f'{date} om {time}'
    moment = ContactTimeslot.query.filter(ContactTimeslot.date == date, ContactTimeslot.organization == organization).first()
    double_response = ContactResponse.query.filter(ContactResponse.timeslot==timeslot, ContactResponse.invite==invite).all()
    if double_response and not email_from_suc:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment=contactmoment, organization=organization,
                               email_token=email_token, error='double_booked')
    max_subscriptions = moment.nbr_sessions
    nbr_subscriptions = ContactResponse.query.filter(ContactResponse.timeslot == timeslot,
                                                     ContactResponse.organization == organization).count()
    if nbr_subscriptions >= max_subscriptions:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment=contactmoment, organization=organization,
                               email_token=email_token, error='max_subscriptions')
    current_year = datetime.datetime.now().year
    timeslot_date = datetime.datetime.strptime(timeslot.split(' ')[1] + str(current_year), '%d/%m-%H.%M%Y')
    response = ContactResponse(timeslot=timeslot, timeslot_date=timeslot_date, invite=invite, organization=organization)
    db.session.add(response)
    db.session.commit()
    return render_template('success_contactmoment.html', title='Bedankt', email=email, contactmoment=contactmoment,
                           organization=organization, email_token=email_token, info='subscribed')


def send_email(organization, email_info):
    key = '_'.join([organization, 'email_sender'])
    email_sender = Setting.query.filter(Setting.key == key).first().value
    msg = Message(subject=email_info['subject'], sender=email_sender, recipients=[email_info['to']])
    msg.html = email_info['body']
    try:
        mail.send(msg)
        return True
    except Exception as e:
        log.error(f'send_email: ERROR, could not send email: {e}')
    return False


send_email_config = [
    {'function': send_email_with_link_to_subscribe_for_contactmoment, 'args': {'org': 'SUI'}},
    {'function': send_email_with_ack_of_contactmoment, 'args': {'org': 'SUI'}},
    {'function': send_email_with_link_to_subscribe_for_contactmoment, 'args': {'org': 'SUMLPU'}},
    {'function': send_email_with_ack_of_contactmoment, 'args': {'org': 'SUMLPU'}},
]

run_email_task = True
def send_email_task():
    nbr_sent_per_minute = 0
    while run_email_task:
        with flask_app.app_context():
            at_least_one_email_sent = True
            start_time = datetime.datetime.now()
            job_interval = int(Setting.query.filter(Setting.key == 'email_task_interval').first().value)
            emails_per_minute = int(Setting.query.filter(Setting.key == 'emails_per_minute').first().value)
            while at_least_one_email_sent:
                at_least_one_email_sent = False
                for send_email in send_email_config:
                    if run_email_task:
                        ret = send_email['function'](**send_email['args'])
                        if ret:
                            nbr_sent_per_minute += 1
                            now = datetime.datetime.now()
                            delta = now - start_time
                            if (nbr_sent_per_minute >= emails_per_minute) and (delta < datetime.timedelta(seconds=60)):
                                time_to_wait = 60 - delta.seconds + 1
                                log.info(f'send_email_task: have to wait for {time_to_wait} seconds')
                                time.sleep(time_to_wait)
                                nbr_sent_per_minute = 0
                                start_time = datetime.datetime.now()
                            at_least_one_email_sent = True
        if run_email_task:
                now = datetime.datetime.now()
                delta = now - start_time
                if delta < datetime.timedelta(seconds=job_interval):
                    time_to_wait = job_interval - delta.seconds
                    time.sleep(time_to_wait)

def stop_send_email_task():
    global run_email_task
    run_email_task = False

def start_send_email_task():
    running_job = scheduler.get_job('send_email_task')
    if running_job:
        scheduler.remove_job('send_email_task')
    scheduler.add_job('send_email_task', send_email_task)

start_send_email_task()

def enable_invite(organization, enable=None):
    if enable == True or enable == False:
        invites = Invite.query.filter(Invite.organization == organization).all()
        for invite in invites:
            invite.enable = enable
        db.session.commit()
        return enable
    enabled_invites_count = Invite.query.filter(Invite.active == True, Invite.enable == True,
                                                Invite.organization == organization).count()
    total_invites_count = Invite.query.filter(Invite.active == True, Invite.organization == organization).count()
    return enabled_invites_count == total_invites_count


js_to_db = {
    'invite_contactmoment': 'BOOL:send_invite_contactmoment_email',
    'response_contactmoment': 'BOOL:send_ack_contactmoment_email',
    'enable_invite': 'FUNC:enable_invite',
    'template_invite_contactmoment': 'TEXT:template_invite_contactmoment',
    'template_ack_contactmoment': 'TEXT:template_ack_contactmoment',
}

@flask_app.route('/settings/<string:organization>', methods=['GET', 'POST'])
@login_required
def settings(organization=None):
    settings_info = {}
    for key, type_key in js_to_db.items():
        try:
            type, setting_key = type_key.split(':')
            if type != 'FUNC':
                setting_key = organization + '_' + setting_key
            if type == 'BOOL':
                setting = Setting.query.filter(Setting.key == setting_key).first().value
                setting = int(setting)
                settings_info[key] = True if setting == 1 else False
            elif type == 'TEXT':
                setting = Setting.query.filter(Setting.key == setting_key).first().value
                settings_info[key] = setting
            elif type == 'FUNC':
                this_module = sys.modules[__name__]
                function = getattr(this_module, setting_key)
                settings_info[key] = function()
        except Exception:
            pass

    info = {
        'nbr_email_addresses': Invite.query.filter(Invite.active == True, Invite.organization == 'SUI').count(),
        'nbr_email_addresses_enabled': Invite.query.filter(Invite.active == True, Invite.enable == True,
                                                           Invite.organization == 'SUI').count(),
        'nbr_invite_contactmoment_sent': Invite.query.filter(Invite.contactmoment_sent == True,
                                                             Invite.organization == 'SUI',
                                                            Invite.active == True, Invite.enable == True).count(),
        'nbr_response_contactmoment_sent': ContactResponse.query.filter(ContactResponse.email_sent == True,
                                                                     ContactResponse.organization == 'SUI').count(),
        'nbr_response_contactmoment': ContactResponse.query.filter(ContactResponse.organization == 'SUI').count(),
        'organization': organization,
    }
    info.update(settings_info)
    return render_template('settings.html', title=organization, info=info, organization=organization)


@flask_app.route('/update_settings/<string:jds>', methods=['GET', 'POST'])
@login_required
def update_settings(jds):
    try:
        jd = json.loads(jds)
        organization = jd['organization']
        settings = jd['settings']
        for key, value in settings.items():
            type, setting_key = js_to_db[key].split(':')
            setting_key = organization + '_' + setting_key
            setting = Setting.query.filter(Setting.key == setting_key).first()
            if type == 'BOOL':
                setting.value = 1 if value else 0
            elif type == 'TEXT':
                setting.value = value
            elif type == 'FUNC':
                this_module = sys.modules[__name__]
                function = getattr(this_module, setting_key)
                function(value)
        db.session.commit()
    except Exception as e:
        log.error(f'Could not update settings : {e}')
        return jsonify({'status': False})
    return jsonify({'status': True})


@flask_app.route('/trigger_settings/<string:jds>', methods=['GET', 'POST'])
@login_required
def trigger_settings(jds):
    try:
        setting = json.loads(jds)
        if setting['id'] == 'email-activity':
            enable_invite(setting['org'], setting['state'])
    except Exception as e:
        log.error(f'Could not trigger setting : {e}')
        return jsonify({'status': False})
    return jsonify({'status': True})


@flask_app.route('/trigger_action/<string:jds>', methods=['GET', 'POST'])
def trigger_action(jds):
    action = json.loads(jds)
    try:
        if action['action'] == 'resend-contact-invite':
            invite_id = action['id']
            invite = Invite.query.get(invite_id)
            invite.contactmoment_sent = False
            db.session.commit()
            return jsonify({'status': True, 'msg': 'Uitnodiging is verstuurd.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan uitnodiging niet sturen.<br>{e}'})
    try:
        if action['action'] == 'add-invite':
            first_name = action['first_name']
            last_name = action['last_name']
            email = action['email']
            organization = action['organization']
            invite = Invite.query.filter(Invite.email == email, Invite.organization == organization).first()
            if invite:
                return jsonify({'status': False, 'msg': 'E-mailadres bestaat al'})
            invite = Invite(first_name=first_name, last_name=last_name, email=email, organization=organization)
            db.session.add(invite)
            db.session.commit()
            update_email_tokens()
            return jsonify({'status': True, 'msg': 'E-mailadres is toegevoegd.<br>Uitnodiging wordt verstuurd.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan e-mailadres niet toevoegen.<br>{e}'})
    try:
        if action['action'] == 'update-invite':
            first_name = action['first_name']
            last_name = action['last_name']
            email = action['email']
            organization = action['organization']
            invite_id = action['id']
            invite = Invite.query.get(invite_id)
            if not invite:
                return jsonify({'status': False, 'msg': 'E-mailadres niet gevonden'})
            invite.first_name = first_name
            invite.last_name = last_name
            db.session.commit()
            return jsonify({'status': True, 'msg': 'E-mailadres is aangepast.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan e-mailadres niet aanapssen.<br>{e}'})
    try:
        if action['action'] == 'remove-subscription':
            response_id = action['id']
            response = ContactResponse.query.get(response_id)
            db.session.delete(response)
            db.session.commit()
            return jsonify({'status': True, 'msg': 'Afspraak is verwijderd.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan afspraak niet verwijderen.<br>{e}'})
    try:
        if action['action'] == 'remove-invite':
            invite_id = action['id']
            invite = Invite.query.get(invite_id)
            db.session.delete(invite)
            db.session.commit()
            return jsonify({'status': True, 'msg': 'E-mailadres is verwijderd.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan e-mailadres niet verwijderen.<br>{e}'})
    try:
        if action['action'] == 'toggle-activation':
            invite_id = action['id']
            invite = Invite.query.get(invite_id)
            invite.active = not invite.active
            db.session.commit()
            return jsonify({'status': True, 'msg': 'Activatie is aangepast.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan activatie niet aanpassen.<br>{e}'})


    try:
        if action['action'] == 'resend-not-responded':
            responses = ContactResponse.query.filter(ContactResponse.organization == 'SUMLPU').all()
            invites = Invite.query.filter(Invite.organization == 'SUMLPU', Invite.enable == True).all()
            response_invit_first_last_name = [f'{r.invite.first_name}{r.invite.last_name}' for r in responses]
            nbr_sent = 0
            for i in invites:
                if not f'{i.first_name}{i.last_name}' in response_invit_first_last_name:
                    i.contactmoment_sent = False
                    nbr_sent += 1
            db.session.commit()
            return jsonify({'status': True, 'msg': f'{nbr_sent} e-mail(s) is/zijn verstuurd.'})
    except Exception as e:
        log.error(f'Could not do action : {e}')
        return jsonify({'status': False, 'msg': f'Kan activatie niet aanpassen.<br>{e}'})
    return jsonify({'status': True})


@flask_app.route('/update_email_template/', methods=['POST'])
@login_required
def update_email_template():
    try:
        key = request.values['template_id']
        organization = request.values['organization']
        content = request.values['content']
        key = organization + '_' + key
        template = Setting.query.filter(Setting.key == key).first()
        template.value = content
        db.session.commit()
    except Exception as e:
        log.error(f'Could not update template : {e}')
        return jsonify({'status': False})
    return jsonify({'status': True})


#e.g. curl 'localhost:5000/test_invite_infomoment?token=Jkj@9_4kj2@Lkl12&email=emmanuel.borowski@gmail.com&nbr=1'
@flask_app.route('/test_invite_infomoment', methods=['GET', 'POST'])
def test_invite_infomoment():
    try:
        random.seed()
        token=request.args.get('token')
        email = request.args.get('email')
        nbr_to_send = int(request.args.get('nbr'))
        if token != flask_app.config['TEST_TOKEN']:
            return 'NOK, bad token\n'
        invite = Invite.query.filter(Invite.email == email).first()
        if not invite:
            return 'NOK, email not found\n'
        links = Link.query.filter(Link.enabled == True).all()
        link = random.choice(links)
        id = '-'.join(['chkbx', str(link.timeslot.id), str(link.topic.id)])
        save_infomoment2(id, invite.email, invite.token, test=True)
    except Exception as e:
        return 'NOK\n'
    return 'OK\n'


