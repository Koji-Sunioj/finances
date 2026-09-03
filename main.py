from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from passlib.context import CryptContext
from utils.functions import decode_token, create_token, breadcrumbs, cursor, execute_db, insert_expenditure

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


@app.get("/home/expenditures", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def welcome(request: Request):
    select_user_id = "select user_id from users where username=%s;"

    execute_db(select_user_id, (request.state.sub,))
    user_id = cursor.fetchone()["user_id"]

    select_expenditures = "select expenditure_id,substring(created::varchar,0,11) as created,name,type,value,frequency from expenditures where user_id=%s;"
    execute_db(select_expenditures, (user_id,))
    expenditures = cursor.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="expenditures.html",
        context={"expenditures": expenditures}
    )


@app.get("/home/expenditures/one-off", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-one-off-expenditure.html",
    )


@app.post("/home/expenditures/one-off", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    payload = await request.form()
    expenditure_id = insert_expenditure(payload, request.state.sub, "one-off")

    insert_one_off = "insert into one_offs (expenditure_id,occur_date) values (%s,%s);"
    execute_args = (expenditure_id, payload["occur_date"])
    execute_db(insert_one_off, execute_args)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)


@app.get("/home/expenditures/daily", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-daily-expenditure.html",
    )


@app.post("/home/expenditures/daily", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def create_daily_expenditure(request: Request):
    payload = await request.form()

    expenditure_id = insert_expenditure(payload, request.state.sub, "daily")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_daily = "insert into dailys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s);"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    execute_db(insert_daily, execute_args)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)


@app.get("/home/expenditures/weekly", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-weekly-expenditure.html",
    )


@app.post("/home/expenditures/weekly", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    payload = await request.form()

    expenditure_id = insert_expenditure(payload, request.state.sub, "weekly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_weekly = "insert into weeklys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning weekly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    execute_db(insert_weekly, execute_args)

    weekly_id = cursor.fetchone()["weekly_id"]
    weekly_days = payload.getlist("weekly_days")

    insert_weekly_days = "insert into weekly_days (weekly_id,week_day) values"
    insert_days = ",".join(["(%s,%s)" % (weekly_id, day)
                           for day in weekly_days])
    insert_command = "%s %s;" % (insert_weekly_days, insert_days)
    execute_db(insert_command)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)


@app.get("/home/expenditures/monthly", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-monthly-expenditure.html",
    )


@app.post("/home/expenditures/monthly", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
async def daily_expenditure(request: Request):
    payload = await request.form()

    expenditure_id = insert_expenditure(payload, request.state.sub, "monthly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_monthly = "insert into monthlys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning monthly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    execute_db(insert_monthly, execute_args)

    monthly_id = cursor.fetchone()["monthly_id"]
    monthly_days = payload.getlist("monthly_days")

    insert_monthly_days = "insert into monthly_days (monthly_id,month_day) values"
    insert_days = ",".join(["(%s,%s)" % (monthly_id, day)
                           for day in monthly_days])
    insert_command = "%s %s;" % (insert_monthly_days, insert_days)
    execute_db(insert_command)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)
