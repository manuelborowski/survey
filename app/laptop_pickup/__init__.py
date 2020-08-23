from flask import Blueprint

laptop_pickup = Blueprint('laptop_pickup', __name__)
from . import routes