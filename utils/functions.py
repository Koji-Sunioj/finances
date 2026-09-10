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

            has_detail = hasattr(error, "detail")
            has_error_code = hasattr(error, "status_code")

            status_code = error.status_code if has_error_code else 400
            detail = None

            match error.__class__.__name__:
                case "UniqueViolation":
                    detail = "that value already exists"
                case _:
                    detail = error.detail if has_detail else "an error occurred"

            raise HTTPException(status_code=status_code, detail=detail)

    return transaction


def insert_expenditure(payload, user_id, frequency):
    insert_expenditure = "insert into expenditures (user_id,name,type,value,frequency) values (%s,%s,%s,%s,%s) returning expenditure_id;"
    execute_args = (
        user_id,
        payload["name"],
        payload["type"],
        payload["value"],
        frequency,
    )

    cursor.execute(insert_expenditure, execute_args)
    expenditure_id = cursor.fetchone()["expenditure_id"]
    return expenditure_id


def breadcrumbs(url):
    uri_pattern = re.search(r"(?<=http:\/\/localhost:8000).+", url)
    uri = uri_pattern.group(0)
    uris = [re.sub(r"\?.+", "", crumb) for crumb in uri.split("/") if len(crumb) > 0]

    breadcrumbs = []
    with_query = {"expenditures": "?sort=starting&direction=ascending"}

    for breadcrumb in uris:
        full_url = uri[0 : uri.index(breadcrumb) + len(breadcrumb)]

        if breadcrumb in with_query:
            full_url += with_query[breadcrumb]

        breadcrumbs.append({"url": full_url, "name": breadcrumb})

    return breadcrumbs


def decode_token(request: Request):
    try:
        uri_pattern = re.search(r"(?<=http:\/\/localhost:8000).+", str(request.url))
        uri = uri_pattern.group(0)

        token_pattern = re.search(r"token=(.+?)(?=;|$)", request.headers["cookie"])
        jwt_payload = jwt.decode(token_pattern.group(1), key=fe_key)

        request.state.sub = jwt_payload["sub"]
        request.state.breadcrumbs = breadcrumbs(str(request.url))
        request.state.user_id = jwt_payload["user_id"]

        match uri:
            case (
                "/home/expenditures/daily"
                | "/home/expenditures/one-off"
                | "/home/expenditures/weekly"
            ):
                request.state.max_date = date.today().isoformat()
    except Exception as error:

        has_module = hasattr(error, "__module__")

        if has_module and error.__module__ == "jose.exceptions":
            raise HTTPException(status_code=403)
        else:
            raise HTTPException(status_code=400)


def create_token(username, user_id):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=180)

    jwt_payload = {
        "sub": username,
        "user_id": user_id,
        "iat": now,
        "exp": expires,
    }

    token = jwt.encode(jwt_payload, fe_key)
    token_string = "token=%s; Path=/; SameSite=Lax" % token

    return token_string
