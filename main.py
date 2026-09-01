from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

import os
import re
import psycopg2
import traceback
import psycopg2.extras

from jose import jwt
from datetime import timedelta, datetime, timezone
from passlib.context import CryptContext

fe_key = os.getenv("FE_KEY")
pwd_context = CryptContext(schemes="sha256_crypt")


conn = psycopg2.connect(
    database="finances",
    host="localhost",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=5432,
)
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")


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


def execute_db(command, args):
    try:
        cursor.execute(command, args)
        conn.commit()
    except Exception:
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
    token_pattern = re.search(r"token=(.+?)(?=;|$)", request.headers["cookie"])
    jwt_payload = jwt.decode(token_pattern.group(1), key=fe_key)

    request.state.sub = jwt_payload["sub"]
    request.state.breadcrumbs = breadcrumbs(str(request.url))
    return jwt_payload


@app.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    if alert == "unauthorized" and username != None:
        return templates.TemplateResponse(
            request=request,
            name="sign-in.html",
            context={"username": username, "alert": alert},
        )
    return templates.TemplateResponse(request=request, name="sign-in.html")


@app.get("/welcome/expenditures", response_class=HTMLResponse)
async def welcome(request: Request):
    jwt = decode_token(request)
    return templates.TemplateResponse(
        request=request,
        name="cunt.html",
        context={"username": jwt["sub"]},
    )


@app.get("/welcome", response_class=HTMLResponse)
async def welcome(request: Request):
    jwt = decode_token(request)
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={"username": jwt["sub"]},
    )


@app.post("/welcome", response_class=HTMLResponse)
async def authenticate(request: Request):
    payload = await request.form()
    new_account = payload["new-account"] if "new-account" in payload else False

    if new_account:
        new_user_command = "insert into users (username,password) values (%s,%s) returning username,created;"
        execute_db(
            new_user_command,
            (payload["username"], pwd_context.hash(payload["password"])),
        )
        if cursor.rowcount > 0:
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            return templates.TemplateResponse(
                request=request,
                name="welcome.html",
                context={"username": payload["username"]},
            )
        return RedirectResponse(
            "/?alert=unauthorized&username=%s" % payload["username"], status_code=302
        )

    else:
        authenticate_command = (
            "select username, password from users where username = %s;"
        )
        execute_db(authenticate_command, (payload["username"],))
        user = cursor.fetchone()

        authenticated = pwd_context.verify(
            payload["password"], user["password"])

        if authenticated:
            token_string = create_token(payload["username"])
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            return templates.TemplateResponse(
                request=request,
                name="welcome.html",
                headers={"Set-Cookie": token_string},
                context={"username": payload["username"]},
            )
        else:
            return RedirectResponse(
                "/?alert=unauthorized&username=%s" % payload["username"],
                status_code=302,
            )
