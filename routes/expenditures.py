from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Request, Depends, APIRouter, HTTPException

from templates import templates
from utils.functions import decode_token, insert_expenditure, tx, cursor

from datetime import datetime

expenditures = APIRouter(
    prefix="/home/expenditures", dependencies=[Depends(decode_token)]
)


@expenditures.get("", response_class=HTMLResponse)
@tx
async def get_expenditures(
    request: Request,
    sort: str = "starting",
    direction: str = "ascending",
    message: str = None,
):
    invalid_sort = sort not in [
        "modified",
        "name",
        "frequency",
        "starting",
        "ending",
        "type",
        "value",
        "interval",
        "dates",
    ]
    invalid_direction = direction not in ["ascending", "descending"]

    if invalid_sort or invalid_direction:
        raise HTTPException(
            status_code=400, detail="invalid search parameters")

    direction_pointers = {"ascending": "asc", "descending": "desc"}
    sort_by = "order by %s %s" % (sort, direction_pointers[direction])

    select_expenditures = f"select * from (select expenditures.expenditure_id, \
        substring(modified::varchar,0,11) as modified, \
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

    cursor.execute(select_expenditures, (request.state.user_id,))
    expenditures = cursor.fetchall()
    print(vars(request.state))

    return templates.TemplateResponse(
        request=request,
        name="expenditures.html",
        context={
            "expenditures": expenditures,
            "sort": sort,
            "direction": direction,
            "message": message,
        },
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
    expenditure_id = insert_expenditure(
        payload, request.state.user_id, "one-off")

    insert_one_off = "insert into one_offs (expenditure_id,occur_date) values (%s,%s);"
    execute_args = (expenditure_id, payload["occur_date"])
    cursor.execute(insert_one_off, execute_args)

    return RedirectResponse("/home/expenditures", status_code=303)


@expenditures.get("/one-off/{expenditure_id}", response_class=HTMLResponse)
async def get_one_off_item(request: Request, expenditure_id: int):
    select_one_off = "select expenditures.expenditure_id,occur_date::varchar,modified::varchar,name,type,value from one_offs \
            join expenditures on expenditures.expenditure_id = one_offs.expenditure_id where user_id = %s and expenditures.expenditure_id = %s;"
    cursor.execute(select_one_off, (request.state.user_id, expenditure_id))
    one_off = cursor.fetchone()

    return templates.TemplateResponse(
        request=request, name="manage-one-off-expenditure.html", context=one_off
    )


@expenditures.post("/one-off/{expenditure_id}", response_class=HTMLResponse)
async def update_one_off_item(request: Request, expenditure_id: int):
    payload = await request.form()

    update_expenditure = "update expenditures set modified=%s,name=%s,type=%s,value=%s where user_id=%s and expenditure_id=%s;"
    cursor.execute(
        update_expenditure,
        (
            datetime.now(),
            payload["name"],
            payload["type"],
            payload["value"],
            request.state.user_id,
            expenditure_id,
        ),
    )

    update_one_off = "update one_offs set occur_date=%s from expenditures where expenditures.expenditure_id = one_offs.expenditure_id \
            and one_offs.expenditure_id =%s and expenditures.user_id = %s;"
    cursor.execute(
        update_one_off, (payload["occur_date"],
                         expenditure_id, request.state.user_id)
    )
    message = "expenditure %s: %s with type %s updated" % (
        expenditure_id,
        payload["name"],
        payload["type"],
    )

    return RedirectResponse(
        "/home/expenditures?sort=starting&direction=ascending&message=%s" % message,
        status_code=303,
    )


@expenditures.post("/one-off/{expenditure_id}/delete", response_class=HTMLResponse)
async def delete_one_off_item(request: Request, expenditure_id: int):
    delete_one_off = "delete from expenditures where expenditure_id = %s and user_id = %s returning name, type;"
    cursor.execute(delete_one_off, (expenditure_id, request.state.user_id))
    result = cursor.fetchone()
    message = "expenditure %s: %s with type %s deleted" % (
        expenditure_id,
        result["name"],
        result["type"],
    )
    return RedirectResponse(
        "/home/expenditures?sort=starting&direction=ascending&message=%s" % message,
        status_code=303,
    )


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

    expenditure_id = insert_expenditure(
        payload, request.state.user_id, "daily")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_daily = "insert into dailys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s);"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    cursor.execute(insert_daily, execute_args)

    return RedirectResponse("/home/expenditures", status_code=302)


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

    expenditure_id = insert_expenditure(
        payload, request.state.user_id, "weekly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_weekly = "insert into weeklys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning weekly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    cursor.execute(insert_weekly, execute_args)

    weekly_id = cursor.fetchone()["weekly_id"]
    weekly_days = payload.getlist("weekly_days")

    insert_weekly_days = "insert into weekly_days (weekly_id,week_day) values"
    insert_days = ",".join(["(%s,%s)" % (weekly_id, day)
                           for day in weekly_days])
    insert_command = "%s %s;" % (insert_weekly_days, insert_days)
    cursor.execute(insert_command)

    return RedirectResponse("/home/expenditures", status_code=302)


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

    expenditure_id = insert_expenditure(
        payload, request.state.user_id, "monthly")

    end_date = payload["end_date"] if len(payload["end_date"]) > 0 else None
    skip = payload["skip"] if len(payload["skip"]) > 0 else None

    insert_monthly = "insert into monthlys (expenditure_id,start_date,end_date,skip) values (%s,%s,%s,%s) returning monthly_id;"
    execute_args = (expenditure_id, payload["start_date"], end_date, skip)
    cursor.execute(insert_monthly, execute_args)

    monthly_id = cursor.fetchone()["monthly_id"]
    monthly_days = payload.getlist("monthly_days")

    insert_monthly_days = "insert into monthly_days (monthly_id,month_day) values"
    insert_days = ",".join(["(%s,%s)" % (monthly_id, day)
                           for day in monthly_days])
    insert_command = "%s %s;" % (insert_monthly_days, insert_days)
    cursor.execute(insert_command)

    return RedirectResponse("/home/expenditures", status_code=302)
