from fastapi import Request, Depends, APIRouter
from templates import templates
from utils.functions import (
    decode_token,
    tx,
    cursor,
    date_list,
    week_to_date,
    month_from_cycle,
    bar_chart_image,
    pie_chart_image,
    log_chart_image,
    pie_chart_groupings
)

import datetime
from pprint import pprint
from datetime import timedelta, date, datetime

forecast = APIRouter(
    prefix="/home/forecast", dependencies=[Depends(decode_token)]
)


# forecast

@forecast.get("")
@tx
async def get_forecast(request: Request, start_date: str = None, end_date: str = None, balance: float = None,
                       bar_chart: str = None, pie_chart: str = None, log_chart: str = None, view_type: str = None):
    if all([start_date, end_date, balance]):
        start_bill = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_bill = datetime.strptime(end_date, "%Y-%m-%d").date()
        bill_days = []

        select_one_offs = "select expenditures.expenditure_id,name,type,value::float,frequency,occur_date from one_offs \
            join expenditures on one_offs.expenditure_id = expenditures.expenditure_id where user_id = %s;"
        cursor.execute(select_one_offs, (request.state.user_id,))
        one_offs = cursor.fetchall()

        for one_off in one_offs:
            if start_bill <= one_off["occur_date"] <= end_bill:
                value = one_off["value"] if one_off["type"] == "deposit" else (
                    - one_off["value"])

                bill_days.append({"type": one_off["type"],
                                  "expenditure_id": one_off["expenditure_id"],
                                  "value": value,
                                  "name": one_off["name"],
                                  "date": one_off["occur_date"],
                                  "type": "one-off"})

        select_dailys = "select expenditures.expenditure_id,name,type,value::float,frequency,start_date,end_date from dailys \
            join expenditures on expenditures.expenditure_id = dailys.expenditure_id where user_id = %s;"
        cursor.execute(select_dailys, (request.state.user_id,))
        dailys = cursor.fetchall()

        for daily in dailys:
            target_end = daily["end_date"] if daily["end_date"] != None and daily["end_date"] <= end_bill else end_bill
            value = daily["value"] if daily["type"] == "deposit" else (
                - daily["value"])

            n_days = int((target_end - daily["start_date"]).days) + 1
            for n in range(n_days):
                bill_day = daily["start_date"] + timedelta(days=n)
                if start_bill <= bill_day <= target_end:
                    bill_days.append({"type": "daily",
                                      "expenditure_id": daily["expenditure_id"],
                                      "value": value,
                                      "name": daily["name"],
                                      "date": bill_day,
                                      })

        select_weeklys = "select expenditures.expenditure_id,value::float,name,type,start_week,start_year,cycles, \
            json_agg(week_day) as days from expenditures \
            join weeklys on weeklys.expenditure_id = expenditures.expenditure_id \
            join weekly_days on weekly_days.weekly_id = weeklys.weekly_id \
            where user_id = %s group by expenditures.expenditure_id,weeklys.weekly_id;"
        cursor.execute(select_weeklys, (request.state.user_id,))
        weeklys = cursor.fetchall()

        end_week_view = end_bill - \
            timedelta(days=end_bill.weekday()) + timedelta(days=6)

        for weekly in weeklys:
            week = int(weekly["start_week"])
            year = int(weekly["start_year"])

            target_week = week_to_date(week, year)
            value = weekly["value"] if weekly["type"] == "deposit" else (
                - weekly["value"])

            if target_week < end_week_view:
                n_weeks = int((end_week_view + timedelta(days=1) - target_week).days /
                              7) if weekly["cycles"] == None else int(weekly["cycles"])
                for i in range(n_weeks):
                    new_week = target_week+timedelta(days=7*i)
                    for day in weekly["days"]:
                        bill_day = new_week + timedelta(days=int(day))
                        if start_bill <= bill_day <= end_bill:
                            bill_days.append({"type": "weekly",
                                              "expenditure_id": weekly["expenditure_id"],
                                              "value": value,
                                              "name": weekly["name"],
                                              "date": bill_day})

        select_monthlys = "select expenditures.expenditure_id,value::float,name,type,start_month,start_year,cycles,json_agg(month_day) days from monthlys \
            join expenditures on expenditures.expenditure_id = monthlys.expenditure_id \
            join monthly_days on monthly_days.monthly_id = monthlys.monthly_id where user_id = %s \
            group by expenditures.expenditure_id,monthlys.monthly_id;"
        cursor.execute(select_monthlys, (request.state.user_id,))
        monthlys = cursor.fetchall()

        end_month_view = end_bill - timedelta(end_bill.day-1)

        for monthly in monthlys:
            first_month = date(monthly["start_year"],
                               monthly["start_month"], 1)
            value = monthly["value"] if monthly["type"] == "deposit" else (
                - monthly["value"])
            bill_months = []

            if first_month <= end_month_view:
                last_month = end_month_view if monthly["cycles"] == None else month_from_cycle(
                    first_month, int(monthly["cycles"]))
                n_days = range((last_month - first_month).days+1)

                for n in n_days:
                    bill_month = first_month + timedelta(days=n)

                    if bill_month.day == 1:
                        bill_months.append(bill_month)

            for bill_month in bill_months:
                for day in monthly["days"]:
                    bill_day = bill_month + timedelta(days=day-1)
                    if bill_day.month == bill_month.month and start_bill <= bill_day <= end_bill:
                        bill_days.append({"type": "monthly",
                                          "expenditure_id": monthly["expenditure_id"],
                                          "value": value,
                                          "name": monthly["name"],
                                          "date": bill_day})

        bill_days = sorted(bill_days, key=lambda x: (x['date']))

        ending_balance = balance
        expenses = 0
        deposits = 0

        for bill_day in bill_days:
            ending_balance += bill_day["value"]
            bill_day["after_expenditure"] = ending_balance

            if bill_day["value"] > 0:
                deposits += bill_day["value"]
            elif bill_day["value"] < 0:
                expenses += bill_day["value"]

        context = {"start_date": start_date, "end_date": end_date, "balance": balance,
                   "ending_balance": ending_balance, "deposits": deposits, "expenses": expenses, "view_type": view_type}

        if bar_chart == "on":
            context["bar_chart"] = bar_chart_image(bill_days)

        if pie_chart == "on":
            expense_names = list({bill["name"]
                                 for bill in bill_days if bill["value"] < 0})
            deposit_names = list({bill["name"]
                                 for bill in bill_days if bill["value"] > 0})

            pie_chart_expenses = pie_chart_groupings(bill_days, expense_names)
            pie_chart_deposits = pie_chart_groupings(bill_days, deposit_names)

            if len(pie_chart_expenses) > 0:
                context["expenses_pie_chart"] = pie_chart_image(
                    pie_chart_expenses, "expenses")

            if len(pie_chart_deposits) > 0:
                context["deposits_pie_chart"] = pie_chart_image(
                    pie_chart_deposits, "deposits")

        if log_chart == "on":
            dates = date_list(start_bill, end_bill)
            context["log_chart"] = log_chart_image(bill_days, dates)

        match view_type:
            case "list":
                context["bill_days"] = bill_days

            case "month":
                dates = dates = date_list(start_bill, end_bill)
                year_months = list(
                    {str(date.year)+"-"+str(date.month) for date in dates})
                bill_months = []

                for year_month in year_months:
                    for bill_day in bill_days:
                        if str(bill_day["date"].year)+"-"+str(bill_day["date"].month) == year_month:
                            append_to_list = True
                            for bill_month in bill_months:
                                if bill_month["month"] == bill_day["date"].month and bill_month["year"] == bill_day["date"].year:
                                    append_to_list = False
                                    bill_month["value"] += bill_day["value"]
                                    bill_month["after_expenditure"] += bill_day["value"]
                                    break
                            if append_to_list:
                                bill_months.append({"month": bill_day["date"].month, "year": bill_day["date"].year,
                                                   "value": bill_day["value"], "after_expenditure": bill_day["after_expenditure"]})
                    
                bill_months.sort(key=lambda bill_month: (bill_month["year"],bill_month["month"]))
                context["bill_months"] = bill_months

            case "week":
                dates = dates = date_list(start_bill, end_bill)
                weeks = list({(date - timedelta(days=date.weekday())) for date in dates})
                bill_weeks = []

                for week in weeks:
                    for bill_day in bill_days:
                        if bill_day["date"] - timedelta(days=bill_day["date"].weekday()) == week:
                            append_to_list = True
                            for bill_week in bill_weeks:
                                if bill_week["year"] == bill_day["date"].year and bill_week["week"] == bill_day["date"].isocalendar()[1]:
                                    append_to_list = False
                                    bill_week["value"] += bill_day["value"]
                                    bill_week["after_expenditure"] += bill_day["value"]
                                    break
                            
                            if append_to_list:
                                bill_weeks.append({"year":week.year,"week":week.isocalendar()[1],
                                                "value":bill_day["value"],"after_expenditure":bill_day["after_expenditure"]})
                
                bill_weeks.sort(key=lambda bill_month: (bill_month["year"],bill_month["week"]))
                context["bill_weeks"] = bill_weeks


        return templates.TemplateResponse(
            request=request,
            name="forecast.html",
            context=context
        )
    else:
        return templates.TemplateResponse(
            request=request,
            name="forecast.html",
        )
