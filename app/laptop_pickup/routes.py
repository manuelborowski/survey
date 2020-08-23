from flask import render_template, flash, redirect, url_for, request, jsonify, current_app
from flask_login import login_required, current_user
from app.forms import LoginForm
from app import  db, log, scheduler, flask_app
from flask_login import login_user, logout_user
from flask_mail import Message
from app.models import Topic, Timeslot, Response, Setting, User, Link, Invite, ContactTimeslot, ContactResponse, update_email_tokens
import numpy, datetime, time, sys, re
import unicodecsv as csv, json, random, urllib.parse
from . import laptop_pickup
import pandas as pd
from app import base

organization = 'SUMLPU'

@laptop_pickup.route(f'/subscribe/{organization}/<string:token>', methods=['GET', 'POST'])
def subscribe_contactmoment(token=None):
    invite = Invite.query.filter(Invite.token == token, Invite.organization == organization).first()
    if not invite:
        return render_template('laptop_pickup/error_contactmoment.html', title='Sorry', error='no_invite')

    contact_table, timeslot_length = base.create_contactmoment_table(organization)
    return render_template('/laptop_pickup/subscribe_contactmoment.html', title='Inschrijven', contact_table=contact_table,
                           email_token=token, email=invite.email, organization=organization, timeslot_length=timeslot_length)


@laptop_pickup.route(f'/save_contactmoment/{organization}', methods=['POST'])
def save_contactmoment():
    if 'who-pickup' in request.form and request.form['who-pickup'] == 'student':
        email = request.form['email']
        email_token = request.form['email_token'] if 'email_token' in request.form else None
        invite = Invite.query.filter(Invite.email == email, Invite.organization == organization).first()
        if not invite:
            return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=organization,
                                   email_token=email_token, error='no_invite')
        response = ContactResponse.query.filter(ContactResponse.invite == invite, ContactResponse.organization == organization).first()
        if response:
            response.info = 'student'
            response.email_sent = False
        else:
            response = ContactResponse(timeslot=None, timeslot_date=None, invite=invite, organization=organization, info='student')
            db.session.add(response)
        db.session.commit()
        return render_template('laptop_pickup/success_contactmoment.html', title='Bedankt', info='subscribed')
    return base.save_contactmoment(request)
