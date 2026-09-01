from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

import os
import psycopg2
import traceback
import psycopg2.extras

from passlib.context import CryptContext

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


def execute_db(command, args):
    try:
        cursor.execute(command, args)
        conn.commit()
    except Exception as error:
        conn.rollback()


@app.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    if alert == "unauthorized" and username != None:
        return templates.TemplateResponse(
            request=request,
            name="sign-in.html",
            context={"username": username, "alert": alert},
        )
    return templates.TemplateResponse(request=request, name="sign-in.html")


@app.post("/welcome", response_class=HTMLResponse)
async def welcome_user(request: Request):
    payload = await request.form()
    new_account = payload["new-account"] if "new-account" in payload else False
    print(payload)

    if new_account:
        new_user_command = "insert into users (username,password) values (%s,%s) returning username,created;"
        execute_db(
            new_user_command,
            (payload["username"], pwd_context.hash(payload["password"])),
        )
        if cursor.rowcount > 0:
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

        authenticated = pwd_context.verify(payload["password"], user["password"])

        if authenticated:
            return templates.TemplateResponse(request=request, name="welcome.html")
        else:
            return RedirectResponse(
                "/?alert=unauthorized&username=%s" % payload["username"],
                status_code=302,
            )
