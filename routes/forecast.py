from fastapi import Request, Depends, APIRouter
from templates import templates
from utils.functions import (
    decode_token,
    tx,
    cursor,
    week_to_date,
    month_from_cycle
)

import io
import base64
import datetime
import matplotlib.pyplot as plt

from pprint import pprint
from datetime import timedelta, date, datetime
from functools import reduce

forecast = APIRouter(
    prefix="/home/forecast", dependencies=[Depends(decode_token)]
)


# forecast

@forecast.get("")
@tx
async def get_forecast(request: Request, start_date: str = None, end_date: str = None, balance: float = None, bar_chart: str = None, pie_chart: str = None):
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
        cursor.execute(select_monthlys,(request.state.user_id,))
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

        context = {"start_date": start_date,
                     "end_date": end_date, "balance": balance, "bill_days": bill_days,
                     "ending_balance": ending_balance, "deposits": deposits, "expenses": expenses}

        if bar_chart == "on":
            expense_names = []

            for bill in bill_days:
                if bill["name"] not in expense_names:
                    expense_names.append(bill["name"])

            expenses = [{"name":expense,"value": 0} for expense in expense_names.copy()]

            for expense in expenses:
                for bill in bill_days:
                    if bill["name"] == expense["name"]:
                        expense["value"] += bill["value"]

            expenses.sort(key=lambda expense: expense['value'])

            ax = plt.subplots()[1]
            bar_container = ax.bar([expense["name"] for expense in expenses],[expense["value"] for expense in expenses],color=["g" if expense["value"] > 0 else "r" for expense in expenses]) 
            ax.bar_label(bar_container)
            ax.axhline(y=0,linewidth=1, color='k')

            plt.title("period: %s through %s" % (start_date, end_date))
            plt.xlabel("name")
            plt.ylabel("amount")
            plt.tight_layout()
            
            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png')
            plt.close()

            base64_encoded_image = base64.b64encode(img_buf.getvalue()).decode("utf-8")
            context["bar_chart"] = base64_encoded_image

        if pie_chart == "on":
            expense_names = []
            deposit_names = []

            for bill in bill_days:
                if bill["value"] > 0 and bill["name"] not in deposit_names:
                    deposit_names.append(bill["name"])
                elif bill["value"] < 0 and bill["name"] not in expense_names:
                    expense_names.append(bill["name"])
            
            expenses = [{"name":expense,"value": 0} for expense in expense_names.copy()]
            deposits = [{"name":deposit,"value": 0} for deposit in deposit_names.copy()]

            for expense in expenses:
                for bill in bill_days:
                    if bill["name"] == expense["name"]:
                        expense["value"] += bill["value"]

            for deposit in deposits:
                for bill in bill_days:
                    if bill["name"] == deposit["name"]:
                        deposit["value"] += bill["value"]

            total_expenses = sum([abs(expense["value"]) for expense in expenses])

            small_values = []

            for expense in expenses:
                if abs(expense["value"]) * 100 / total_expenses < 10:
                    small_values.append(expense)

            expenses = [expense for expense in expenses.copy() if abs(expense["value"]) * 100 / total_expenses > 10]

            small_name,small_name = None, None

            if len(small_values) > 1:
                small_name = reduce(lambda result, current: result["name"] +",\n"+ current["name"], small_values)
                small_value = reduce(lambda result, current: result["value"] + current["value"], small_values)
            else:
                small_name, small_value = small_values[0]["name"], small_values[0]["value"]
            
            expenses.append({"name":small_name,"value":small_value})

            ax = plt.subplots()[1]
            ax.pie([abs(expense["value"]) for expense in expenses],autopct='%1.1f%%',labels=[expense["name"] for expense in expenses])
            plt.title("expense share")
            plt.tight_layout()
            
            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png')
            plt.close()

            base64_encoded_image = base64.b64encode(img_buf.getvalue()).decode("utf-8")
            context["pie_chart"] = base64_encoded_image

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
