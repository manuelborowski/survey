from .models import ContactTimeslot, ContactResponse, Invite
from flask import render_template
import datetime
from app import db


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


def create_contactmoment_table(organization, decode_time_cb=None):
    if not decode_time_cb:
        decode_time_cb = decode_time
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


def save_contactmoment(request):
    organization = request.form['organization']
    email = request.form['email']
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
    moment = ContactTimeslot.query.filter(ContactTimeslot.date == date,
                                          ContactTimeslot.organization == organization).first()
    # double_response = ContactResponse.query.filter(ContactResponse.timeslot == timeslot,
    #                                                ContactResponse.invite == invite).all()
    # if double_response and not email_from_suc:
    #     return render_template('error_contactmoment.html', title='Sorry', contactmoment=contactmoment,
    #                            organization=organization,
    #                            email_token=email_token, error='double_booked')
    max_subscriptions = moment.nbr_sessions
    nbr_subscriptions = ContactResponse.query.filter(ContactResponse.timeslot == timeslot,
                                                     ContactResponse.organization == organization).count()
    if nbr_subscriptions >= max_subscriptions:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment=contactmoment,
                               organization=organization, email_token=email_token, error='max_subscriptions')
    current_year = datetime.datetime.now().year
    timeslot_date = datetime.datetime.strptime(timeslot.split(' ')[1] + str(current_year), '%d/%m-%H.%M%Y')
    response = ContactResponse.query.filter(ContactResponse.invite == invite, ContactResponse.organization == organization).first()
    if response:
        response.timeslot = timeslot
        response.timeslot_date = timeslot_date
        response.info = ''
        response.email_sent = False
    else:
        response = ContactResponse(timeslot=timeslot, timeslot_date=timeslot_date, invite=invite, organization=organization)
        db.session.add(response)
    db.session.commit()
    return render_template('success_contactmoment.html', title='Bedankt', email=email, contactmoment=contactmoment,
                           organization=organization, email_token=email_token, info='subscribed')
