from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    """The Login Form."""
    accessToken = StringField('Token', validators=[DataRequired()])
    submit = SubmitField('Sign In')
