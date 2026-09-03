from fastapi import Request, Depends, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from templates import templates
from utils.functions import decode_token, cursor, execute_db, insert_expenditure

expenditures = APIRouter(prefix="/expenditures",
                         dependencies=[Depends(decode_token)])


@expenditures.get("/", response_class=HTMLResponse)
async def get_expenditures(request: Request):
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


@expenditures.get("/one-off", response_class=HTMLResponse)
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-one-off-expenditure.html",
    )


@expenditures.post("/one-off", response_class=HTMLResponse)
async def daily_expenditure(request: Request):
    payload = await request.form()
    expenditure_id = insert_expenditure(payload, request.state.sub, "one-off")

    insert_one_off = "insert into one_offs (expenditure_id,occur_date) values (%s,%s);"
    execute_args = (expenditure_id, payload["occur_date"])
    execute_db(insert_one_off, execute_args)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)


@expenditures.get("/daily", response_class=HTMLResponse)
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-daily-expenditure.html",
    )


@expenditures.post("/daily", response_class=HTMLResponse)
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


@expenditures.get("/weekly", response_class=HTMLResponse)
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-weekly-expenditure.html",
    )


@expenditures.post("/weekly", response_class=HTMLResponse)
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


@expenditures.get("/monthly", response_class=HTMLResponse)
async def daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-monthly-expenditure.html",
    )


@expenditures.post("/monthly", response_class=HTMLResponse)
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
