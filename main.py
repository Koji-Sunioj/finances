from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from passlib.context import CryptContext
from utils.functions import decode_token, create_token, breadcrumbs, cursor, execute_db

from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")
pwd_context = CryptContext(schemes="sha256_crypt")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    match exc.status_code:
        case 403:
            return templates.TemplateResponse(
                request=request,
                name="403.html"
            )
        case _:
            return templates.TemplateResponse(
                request=request,
                name="404.html"
            )


@app.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    if alert == "unauthorized" and username != None:
        return templates.TemplateResponse(
            request=request,
            name="sign-in.html",
            context={"username": username, "alert": alert},
        )
    return templates.TemplateResponse(request=request, name="sign-in.html")


@app.post("/home", response_class=HTMLResponse)
async def authenticate(request: Request):
    payload = await request.form()
    account_type = "new-account" if "new-account" in payload and payload["new-account"] == "on" else "current-user"
    auth_result = "unauthorized"

    match account_type:
        case "new-account":
            new_user_command = "insert into users (username,password) values (%s,%s) returning username,created;"
            execute_db(
                new_user_command,
                (payload["username"], pwd_context.hash(payload["password"])),
            )

            if cursor.rowcount > 0:
                auth_result = "new-user"

        case "current-user":
            authenticate_command = (
                "select username, password from users where username = %s;"
            )
            execute_db(authenticate_command, (payload["username"],))
            user = cursor.fetchone()

            if cursor.rowcount > 0:
                authenticated = pwd_context.verify(
                    payload["password"], user["password"])

                if authenticated:
                    auth_result = "authenticated"

    match auth_result:
        case "unauthorized":
            return RedirectResponse(
                "/?alert=unauthorized&username=%s" % payload["username"],
                status_code=302)

        case "authenticated" | "new-user":
            token_string = create_token(payload["username"])
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            return templates.TemplateResponse(
                request=request,
                name="home.html",
                headers={"Set-Cookie": token_string},
                context={"username": payload["username"]},
            )


@app.get("/home", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html"
    )


@app.get("/home/expenditures/manage", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def welcome(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-expenditures.html",
    )


@app.get("/home/expenditures", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def welcome(request: Request):
    select_user_id = "select user_id from users where username=%s;"

    execute_db(select_user_id, (request.state.sub,))
    user_id = cursor.fetchone()["user_id"]

    select_expenditures = "select expense_id,name,type,frequency,\
        value,start_date,end_date,interval from expenditures where user_id=%s;"

    execute_db(select_expenditures, (user_id,))

    expenditures = cursor.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="expenditures.html",
        context={"expenditures": expenditures}
    )


@app.get("/home/expenditures/manage/{expenditure_id}", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def welcome(request: Request, expenditure_id: int):
    select_user_id = "select user_id from users where username=%s;"

    execute_db(select_user_id, (request.state.sub,))
    user_id = cursor.fetchone()["user_id"]

    select_expenditure = "select expense_id,name,type,frequency,\
        value,start_date,end_date,interval from expenditures where \
        user_id=%s and expense_id=%s;"

    execute_db(select_expenditure, (user_id, expenditure_id))

    expenditure = cursor.fetchone()
    print(expenditure)

    return templates.TemplateResponse(
        request=request,
        name="manage-expenditures.html",
        context={"expenditure": expenditure}
    )


@app.post("/home/expenditures/manage", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def welcome(request: Request):
    payload = await request.form()
    select_user_id = "select user_id from users where username=%s;"

    execute_db(select_user_id, (request.state.sub,))
    user_id = cursor.fetchone()["user_id"]

    match payload["frequency"]:
        case "one-off":
            one_off_insert = "insert into expenditures (user_id,name,type,frequency,value\
                ,start_date) values (%s,%s,%s,%s,%s,%s);"
            execute_db(one_off_insert, (user_id, payload["name"], payload["type"],
                       payload["frequency"], payload["value"], payload["start_date"]))
        case "daily":
            end_date = payload["end_date"] if len(
                payload["end_date"]) > 0 else None
            interval = payload["interval"] if len(
                payload["interval"]) > 0 else None

            daily_insert = "insert into expenditures (user_id,name,type,frequency,value,\
                start_date,end_date,interval) values (%s,%s,%s,%s,%s,%s,%s,%s);"
            execute_db(daily_insert, (user_id, payload["name"], payload["type"],
                       payload["frequency"], payload["value"], payload["start_date"], end_date, interval))

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)
