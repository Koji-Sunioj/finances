import re
import os
import psycopg2
import psycopg2.extras

from jose import jwt
from functools import wraps
from traceback import format_exc
from fastapi import Request, HTTPException
from datetime import datetime, timedelta, timezone, date

fe_key = os.getenv("FE_KEY")

conn = psycopg2.connect(
    database="finances",
    host="localhost",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=5432,
)
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def tx(function):
    @wraps(function)
    async def transaction(*args, **kwargs):
        try:
            executed = await function(*args, **kwargs)
            conn.commit()
            return executed
        except Exception as error:
            conn.rollback()
            print("error type: %s" % error.__class__.__name__)
            print(format_exc())

            has_detail = hasattr(error, 'detail')
            has_error_code = hasattr(error, 'status_code')

            status_code = error.status_code if has_error_code else 400
            detail = error.detail if has_detail else "an error occurred"

            raise HTTPException(status_code=status_code, detail=detail)

    return transaction


def insert_expenditure(payload, username, frequency):
    select_user_id = "select user_id from users where username=%s;"
    cursor = execute_db(select_user_id, (username,))
    user_id = cursor.fetchone()["user_id"]

    insert_expenditure = "insert into expenditures (user_id,name,type,value,frequency) values (%s,%s,%s,%s,%s) returning expenditure_id;"
    execute_args = (user_id, payload["name"],
                    payload["type"], payload["value"], frequency)
    cursor = execute_db(insert_expenditure, execute_args)

    expenditure_id = cursor.fetchone()["expenditure_id"]
    return expenditure_id


def execute_db(command, args=None):
    try:
        cursor.execute(command, args)
        conn.commit()
        return cursor
    except Exception as error:
        print(format_exc(error))
        conn.rollback()


def breadcrumbs(url):
    uri_pattern = re.search(
        r"(?<=http:\/\/localhost:8000).+", url)
    uri = uri_pattern.group(0)
    uris = [crumb for crumb in uri.split("/") if len(crumb) > 0]

    breadcrumbs = []

    for breadcrumb in uris:
        uri_name = breadcrumb
        if "?" in breadcrumb:
            uri_name = ", ".join(breadcrumb.replace("?", ", ").split("&"))
        breadcrumbs.append(
            {"url": uri[0:uri.index(breadcrumb)+len(breadcrumb)], "name": uri_name})

    return breadcrumbs


def decode_token(request: Request):
    try:
        uri_pattern = re.search(
            r"(?<=http:\/\/localhost:8000).+", str(request.url))
        uri = uri_pattern.group(0)

        token_pattern = re.search(
            r"token=(.+?)(?=;|$)", request.headers["cookie"])
        jwt_payload = jwt.decode(token_pattern.group(1), key=fe_key)

        request.state.sub = jwt_payload["sub"]
        request.state.breadcrumbs = breadcrumbs(str(request.url))

        match uri:
            case "/home/expenditures/daily" | "/home/expenditures/one-off" | "/home/expenditures/weekly":
                request.state.max_date = date.today().isoformat()
    except Exception as error:
        print(error)
        raise HTTPException(status_code=403)


def create_token(username):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=180)

    jwt_payload = {
        "sub": username,
        "iat": now,
        "exp": expires,
    }

    token = jwt.encode(jwt_payload, fe_key)
    token_string = "token=%s; Path=/; SameSite=Lax" % token

    return token_string
