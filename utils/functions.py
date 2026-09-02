import re
import os
import psycopg2
import psycopg2.extras

from functools import wraps
from jose import jwt
from traceback import format_exc
from fastapi import Request, HTTPException
from datetime import datetime, timedelta, timezone

fe_key = os.getenv("FE_KEY")

conn = psycopg2.connect(
    database="finances",
    host="localhost",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=5432,
)
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def execute_db(command, args):
    try:
        cursor.execute(command, args)
        conn.commit()
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
        breadcrumbs.append(
            {"url": uri[0:uri.index(breadcrumb)+len(breadcrumb)], "name": breadcrumb})

    return breadcrumbs


def decode_token(request: Request):
    try:
        token_pattern = re.search(
            r"token=(.+?)(?=;|$)", request.headers["cookie"])
        jwt_payload = jwt.decode(token_pattern.group(1), key=fe_key)

        request.state.sub = jwt_payload["sub"]
        request.state.breadcrumbs = breadcrumbs(str(request.url))
    except:
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
