import re
import os
import io
import base64
import psycopg2
import psycopg2.extras
import matplotlib.pyplot as plt

from jose import jwt
from functools import wraps
from traceback import format_exc
from fastapi import Request, HTTPException
from datetime import datetime, timedelta, timezone, date

from pprint import pprint

fe_key = os.getenv("FE_KEY")

conn = psycopg2.connect(
    database="finances",
    host="localhost",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=5432,
)
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def date_list(start_date, end_date):
    date_diff = end_date - start_date
    return [(start_date + timedelta(days=n))for n in range(date_diff.days + 1)]


def group_by_date_type(type: str, bill_days: list, dates: list):
    same_date, increment_existing, indexes, group = None, None, None, None

    match type:
        case "month":
            indexes = list({date - timedelta(days=date.day - 1)
                           for date in dates})

            def same_date(bill_day, index): return bill_day["date"] - timedelta(
                days=bill_day["date"].day - 1) == index

            def increment_existing(
                bill_group, bill_day): return bill_group["month"] == bill_day["date"].month and bill_group["year"] == bill_day["date"].year

            def group(bill_day): return {
                "month": bill_day["date"].month, "year": bill_day["date"].year}
        case "week":
            indexes = list({(date - timedelta(days=date.weekday()))
                           for date in dates})

            def same_date(bill_day, index): return bill_day["date"] - timedelta(
                days=bill_day["date"].weekday()) == index

            def increment_existing(bill_week, bill_day): return bill_week["year"] == (bill_day["date"] - timedelta(
                days=bill_day["date"].weekday())).year and bill_week["week"] == bill_day["date"].isocalendar()[1]

            def group(bill_day): return {"week": bill_day["date"].isocalendar()[
                1], "year": bill_day["date"].year}

    bill_groups = []

    for index in indexes:
        for bill_day in bill_days:
            if same_date(bill_day, index):
                append_to_list = True
                deposits, expenses = 0, 0
                if bill_day["value"] < 0:
                    expenses += bill_day["value"]
                elif bill_day["value"] > 0:
                    deposits += bill_day["value"]
                for bill_group in bill_groups:
                    if increment_existing(bill_group, bill_day):
                        append_to_list = False
                        bill_group["expenses"] += expenses
                        bill_group["deposits"] += deposits
                        bill_group["after_expenditure"] += bill_day["value"]
                        break
                if append_to_list:
                    new_group = group(bill_day)
                    new_group["expenses"] = expenses
                    new_group["deposits"] = deposits
                    new_group["after_expenditure"] = bill_day["after_expenditure"]
                    bill_groups.append(new_group)

    return bill_groups


def week_days():
    return [{"name": "Monday", "value": 0, "selected": False},
            {"name": "Tuesday", "value": 1, "selected": False},
            {"name": "Wednesday", "value": 2, "selected": False},
            {"name": "Thursday", "value": 3, "selected": False},
            {"name": "Friday", "value": 4, "selected": False},
            {"name": "Saturday", "value": 5, "selected": False},
            {"name": "Sunday", "value": 6, "selected": False}]


def real_value(expenditure_type: str, value: float):
    return -value if expenditure_type == "expense" else value


def month_days():
    return [{"value": n, "selected": False} for n in range(1, 32)]


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
    insert_expenditure = "insert into expenditures (user_id,name,type,value,frequency) values (%s,%s,%s,%s,%s) \
        returning expenditure_id, name, type;"
    execute_args = (
        user_id,
        payload["name"],
        payload["type"],
        payload["value"],
        frequency,
    )

    cursor.execute(insert_expenditure, execute_args)
    return cursor.fetchone()


def update_expenditure(payload, user_id, expenditure_id):
    update_expenditure = "update expenditures set modified=%s,name=%s,type=%s,value=%s where user_id=%s and expenditure_id=%s \
        returning expenditure_id, name, type;"
    cursor.execute(
        update_expenditure,
        (
            datetime.now(),
            payload["name"],
            payload["type"],
            payload["value"],
            user_id,
            expenditure_id,
        ),
    )
    return cursor.fetchone()


def delete_expenditure(user_id, expenditure_id):
    delete_expenditure = "delete from expenditures where user_id = %s and expenditure_id = %s \
        returning expenditure_id, name, type"
    cursor.execute(delete_expenditure, (user_id, expenditure_id))
    return cursor.fetchone()


def breadcrumbs(url):
    uri_pattern = re.search(r"(?<=http:\/\/localhost:8000).+", url)
    uri = uri_pattern.group(0)
    uris = [re.sub(r"\?.+", "", crumb)
            for crumb in uri.split("/") if len(crumb) > 0]

    breadcrumbs = []
    with_query = {"expenditures": "?sort=starting&direction=ascending"}

    for breadcrumb in uris:
        full_url = uri[0: uri.index(breadcrumb) + len(breadcrumb)]

        if breadcrumb in with_query:
            full_url += with_query[breadcrumb]

        breadcrumbs.append({"url": full_url, "name": breadcrumb})

    return breadcrumbs


def bar_chart_image(bill_days):
    expenditure_names = list({bill["name"] for bill in bill_days})
    expenditures = [{"name": expenditure, "value": 0}
                    for expenditure in expenditure_names.copy()]

    for expenditure in expenditures:
        for bill in bill_days:
            if bill["name"] == expenditure["name"]:
                expenditure["value"] += bill["value"]

    expenditures.sort(key=lambda expenditure: expenditure['value'])

    ax = plt.subplots()[1]
    ax.barh([expenditure["name"] for expenditure in expenditures], [expenditure["value"]
                                                                    for expenditure in expenditures], color=["g" if expenditure["value"] > 0 else "r" for expenditure in expenditures])
    ax.grid()
    ax.tick_params(axis='x', rotation=20)

    plt.subplots_adjust(hspace=0, bottom=0.2)
    plt.title("expenditures grouped by name")
    plt.xlabel("name")
    plt.ylabel("amount")

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def balance_line(bill_days, dates, balance):
    log_days = [{"date": date, "value": 0} for date in dates]

    for n, log_day in enumerate(log_days):
        for bill_day in bill_days:
            if bill_day["date"] == log_day["date"]:
                log_day["value"] += bill_day["value"]
        if n > 0:
            log_day["value"] += log_days[n - 1]["value"]

    pprint(log_days)

    ax = plt.subplots()[1]
    ax.plot(dates, [log_day["value"] + balance for log_day in log_days])
    ax.set_xlim(dates[0], dates[-1])
    ax.grid()
    ax.tick_params(axis='x', rotation=20)

    if len(log_days) >= 10:
        ax.xaxis.set_major_locator(plt.MaxNLocator(8))

    plt.title("balance over time")
    plt.xlabel("date")
    plt.ylabel("amount")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def pie_chart_image(expenditures, title):
    ax = plt.subplots()[1]
    ax.pie([abs(expenditure["value"]) for expenditure in expenditures],
           autopct='%1.1f%%', labels=[expenditure["name"] for expenditure in expenditures])
    plt.title("{} %".format(title))
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def pie_chart_groupings(bill_days, expenditure_names):
    expenditures = [{"name": expense, "value": 0}
                    for expense in expenditure_names.copy()]

    for expenditure in expenditures:
        for bill in bill_days:
            if bill["name"] == expenditure["name"]:
                expenditure["value"] += bill["value"]

    total_expenditures = sum([abs(expenditure["value"])
                             for expenditure in expenditures])
    small_values = []

    for expenditure in expenditures:
        if abs(expenditure["value"]) * 100 / total_expenditures < 10:
            small_values.append(expenditure)

    expenditures = [expenditure for expenditure in expenditures.copy() if abs(
        expenditure["value"]) * 100 / total_expenditures > 10]

    small_value, small_name = None, None

    if len(small_values) > 1:
        small_name = ",\n".join([something["name"]
                                for something in small_values])
        small_value = sum([something["value"] for something in small_values])
    elif len(small_values) == 1:
        small_name, small_value = small_values[0]["name"], small_values[0]["value"]

    if small_name and small_value:
        expenditures.append({"name": small_name, "value": small_value})

    return expenditures


def decode_token(request: Request):
    try:
        token_pattern = re.search(
            r"token=(.+?)(?=;|$)", request.headers["cookie"])
        jwt_payload = jwt.decode(token_pattern.group(1), key=fe_key)

        request.state.sub = jwt_payload["sub"]
        request.state.breadcrumbs = breadcrumbs(str(request.url))
        request.state.user_id = jwt_payload["user_id"]

        uri_pattern = re.search(
            r"(?<=http:\/\/localhost:8000).+", str(request.url))
        uri = uri_pattern.group(0)
        has_form = re.search(
            r"\/home\/expenditures\/(?=daily|one\-off)|forecast", uri)

        if has_form:
            request.state.max_date = date.today().isoformat()

    except:
        raise HTTPException(status_code=403)


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


def week_to_date(week, year):
    begin_of_year = date(year, 1, 1)
    week_one = begin_of_year - timedelta(days=begin_of_year.weekday())

    if (week_one + timedelta(days=3)).year != year:
        week_one = week_one + timedelta(days=7)

    return week_one + timedelta(days=(week-1)*7)
