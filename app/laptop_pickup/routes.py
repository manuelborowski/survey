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


@laptop_pickup.route('/student_lpu/<string:org>/<string:token>', methods=['GET', 'POST'])
def student_lpu(org, token):
    invite = Invite.query.filter(Invite.token == token, Invite.organization == org).first()
    if not invite:
        return render_template('error_contactmoment.html', title='Sorry', contactmoment='', organization=org,
                               email_token='', error='no_invite')
    response = ContactResponse.query.filter(ContactResponse.invite == invite, ContactResponse.organization == org,
                                            ContactResponse.info == 'student').first()
    if not response:
        response = ContactResponse(invite=invite, organization=org, info='student')
        db.session.add(response)
        db.session.commit()
    return render_template('laptop_pickup/success_student_lpu.html', title='Bedankt', info='subscribed')


