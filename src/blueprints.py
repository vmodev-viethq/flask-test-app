import uuid
import re

from datetime import datetime
from typing import List, Dict

from flask import Blueprint, jsonify, g, request, Response
from sqlalchemy import text

from .db import db

def register_blueprints(app):
    """Register all of our blueprints on the provided Flask app"""
    app.register_blueprint(internal_mails_info_bp)


def validate_integers(integers: Dict) -> List:
    errors = []
    for key, value in integers.items():
        try:
            int(value)
        except Exception as ex:
            errors.append(f"{key} must be integer")
    return errors


def validate_dates(dates: Dict) -> List:
    errors = []
    for key, value in dates.items():
        try:
            if value:
                datetime.strptime(value, '%Y-%m-%d')
        except Exception as ex:
            errors.append(f"{key} must be a date YYYY-MM-DD")
    return errors

MAX_EMAILS_PER_PAGE = 10
DESIRED_PAGE = 1

# Ensure they have provided a `X-Env` and `X-Token` values

internal_mails_info_bp = Blueprint('mall-info', __name__, url_prefix='/internal')

@internal_mails_info_bp.route('/get_user_messages', methods=['GET'])
def get_user_messages():
    user_id = request.args.get('user_id')  # Required
    company_id = request.args.get('company_id')  # Required
    is_admin = request.args.get('is_admin', False)
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)
    emails_per_page = request.args.get('emails_per_page', MAX_EMAILS_PER_PAGE)
    desired_page = request.args.get('desired_page', DESIRED_PAGE)
    search_term = request.args.get('search_term', None)

    # Validations
    errors = validate_integers({
        'emails_per_page': emails_per_page,
        'desired_page': desired_page,
        'user_id': user_id,
        'company_id': company_id,
    })

    if len(errors) > 0:
        return jsonify(f"Validation errors: {errors}"), 400

    if user_id is None or len(user_id) == 0:
        return jsonify(f"""Missing user_id, received {user_id}"""), 400

    if company_id is None or len(company_id) == 0:
        return jsonify(f"""Missing company_id, received {company_id}"""), 400

    # validate emails_per_page
    emails_per_page = int(emails_per_page) if int(emails_per_page) < MAX_EMAILS_PER_PAGE else MAX_EMAILS_PER_PAGE

    # validate desired_page
    desired_page = int(desired_page) if int(desired_page) > 0 else DESIRED_PAGE

    # validate is_admin
    is_admin = is_admin if isinstance(is_admin, bool) else is_admin.lower() == "true"

    offset = (desired_page - 1) * emails_per_page

    # Find message ids
    sql_query = """
        select result.*, count(*) OVER() AS total from (    
            select distinct(m.id), m.sent_at
            from message m
            join recipient r on r.message_id = m.id and r.type in ('to', 'cc') 
            join address a on a.address_id = r.address_id
            where m.company_id = :company_id """

    if is_admin is False:
        sql_query = sql_query + " and a.user_id = :user_id "

    if start_date and end_date:
        sql_query = sql_query + " and cast(m.sent_at as date) between TO_TIMESTAMP(:start_date,'YYYY-MM-DD') and TO_TIMESTAMP(:end_date,'YYYY-MM-DD') "

    if search_term:
        # split the search term into words separated by whitespace
        search_term = '%' + search_term + '%'
        search_term = re.sub(r'\s', '%', search_term)
        sql_query = sql_query + " and m.subject ilike :search_term "

    sql_query = sql_query + "order by m.sent_at desc NULLS last ) as result limit :page_size offset :offset"
    response = db.engine.execute(text(sql_query), user_id=user_id, company_id=company_id, is_admin=is_admin, start_date=start_date,
                                 end_date=end_date, search_term=search_term, page_size=emails_per_page, offset=offset)
    total_rows = 0
    email_ids = []
    for pos, row in enumerate(response):
        email_ids.append(uuid.UUID(str(row['id'])))
        if pos == 0:
            total_rows = row['total'] if total_rows == 0 else total_rows

    if len(email_ids) == 0:
        return jsonify(data=[], total=0, num_pages=0, current_page=0)

    # Get message info + recipients in bulk
    info_query = """
            select * from message m
            join recipient r on r.message_id = m.id and r.type in ('to', 'cc') 
            join address a on a.address_id = r.address_id where m.id in :ids 
            order by m.sent_at desc NULLS last, m.id """
    response = db.engine.execute(text(info_query), ids=tuple(email_ids))
    result = {}
    for row in response:
        message_dict = result.get(str(row['id']))
        if message_dict is None:
            message_dict = {
                'id': str(row['id']),
                'subject': row['subject'],
                'sent_at': row['sent_at'],
                'text': row['text'][:80] if row['text'] else '',
                'html': row['html']
            }

        if row['type'] == 'to':
            message_dict['to'] = {
                'email': row['email'],
                'name': row['name'],
                'user_id': row['user_id']
            }
            # TODO remove this after deprecate inbox v1
            message_dict['name'] = row['name']
            message_dict['user_id'] = row['user_id']
        else:
            cc_list = message_dict.get('cc', [])
            cc_list.append({
                    'email': row['email'],
                    'name': row['name'],
                    'user_id': row['user_id']
                })
            message_dict['cc'] = cc_list

        result[str(row['id'])] = message_dict

    # calculate the total number of pages necessary to represent emails
    num_pages = (total_rows // emails_per_page) + (1 if total_rows % emails_per_page else 0)
    return jsonify(data=[value for value in result.values()], total=total_rows, num_pages=num_pages, current_page=desired_page if result else 0)
