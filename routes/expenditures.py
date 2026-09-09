from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Request, Depends, APIRouter, HTTPException

from templates import templates
from utils.functions import decode_token, execute_db, insert_expenditure, tx

expenditures = APIRouter(prefix="/expenditures",
                         dependencies=[Depends(decode_token)])


@expenditures.get("", response_class=HTMLResponse)
@tx
async def get_expenditures(request: Request, sort: str = "starting", direction: str = "ascending"):
    invalid_sort = sort not in ["created", "name", "frequency",
                                "starting", "ending", "type", "value", "interval", "dates"]
    invalid_direction = direction not in ["ascending", "descending"]

    if invalid_sort or invalid_direction:
        raise HTTPException(
            status_code=400, detail="invalid search parameters")

    select_user_id = "select user_id from users where username=%s;"
    cursor = execute_db(select_user_id, (request.state.sub,))
    user_id = cursor.fetchone()["user_id"]

    direction_pointers = {"ascending": "asc", "descending": "desc"}
    sort_by = "order by %s %s" % (sort, direction_pointers[direction])

    select_expenditures = f"select * from (select expenditures.expenditure_id, \
        substring(created::varchar,0,11) as created, \
        name, type, value, frequency, \
        coalesce(one_offs.occur_date, weeklys.start_date,monthlys.start_date,dailys.start_date) starting, \
        coalesce(weeklys.end_date,monthlys.end_date,dailys.end_date) ending, \
        coalesce(weeklys.skip,monthlys.skip,dailys.skip) interval, \
        case \
            when count(weekly_days.week_day) > 0 then count(weekly_days.week_day) \
            when count(monthly_days.month_day) > 0 then count(monthly_days.month_day) \
        end dates \
    from expenditures \
        left join one_offs on one_offs.expenditure_id = expenditures.expenditure_id \
        left join monthlys on monthlys.expenditure_id = expenditures.expenditure_id \
        left join monthly_days on monthly_days.monthly_id = monthlys.monthly_id \
        left join weeklys on weeklys.expenditure_id = expenditures.expenditure_id \
        left join weekly_days on weekly_days.weekly_id = weeklys.weekly_id \
        left join dailys on dailys.expenditure_id = expenditures.expenditure_id \
    where user_id = %s \
    group by expenditures.expenditure_id, starting, ending, interval {sort_by}) expenditure_values where \
    (expenditure_values.frequency = 'one-off' and expenditure_values.starting >= current_date) or \
	(expenditure_values.frequency != 'one-off' and expenditure_values.ending >= current_date) or \
	(expenditure_values.frequency != 'one-off' and expenditure_values.starting >= current_date and expenditure_values.ending is null);" 

    cursor = execute_db(select_expenditures, (user_id,))
    expenditures = cursor.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="expenditures.html",
        context={"expenditures": expenditures,
                 "sort": sort, "direction": direction}
    )


@expenditures.get("/one-off", response_class=HTMLResponse)
async def get_one_off(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-one-off-expenditure.html",
    )


@expenditures.post("/one-off", response_class=HTMLResponse)
@tx
async def create_one_off(request: Request):
    payload = await request.form()
    expenditure_id = insert_expenditure(payload, request.state.sub, "one-off")

    insert_one_off = "insert into one_offs (expenditure_id,occur_date) values (%s,%s);"
    execute_args = (expenditure_id, payload["occur_date"])
    execute_db(insert_one_off, execute_args)

    return RedirectResponse(
        "/home/expenditures",
        status_code=302)


@expenditures.get("/daily", response_class=HTMLResponse)
async def get_daily_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-daily-expenditure.html",
    )


@expenditures.post("/daily", response_class=HTMLResponse)
@tx
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
async def get_weekly_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-weekly-expenditure.html",
    )


@expenditures.post("/weekly", response_class=HTMLResponse)
@tx
async def create_weekly_expenditure(request: Request):
    payload = await request.form()

    expenditure_id = insert_expenditure(payload, request.state.sub, "weekly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_weekly = "insert into weeklys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning weekly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    cursor = execute_db(insert_weekly, execute_args)

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
async def get_monthly_expenditure(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="manage-monthly-expenditure.html",
    )


@expenditures.post("/monthly", response_class=HTMLResponse)
@tx
async def created_monthly_expenditure(request: Request):
    payload = await request.form()

    expenditure_id = insert_expenditure(payload, request.state.sub, "monthly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_monthly = "insert into monthlys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning monthly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    cursor = execute_db(insert_monthly, execute_args)

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
