create table users (
    user_id serial primary key,
    username varchar unique,
    password varchar,
    created timestamp default now()
);

create table expenditures (
    expenditure_id serial primary key,
    modified timestamp default now(),
    user_id int,
    name varchar unique,
    type varchar check(type in ('expense','deposit')),
    value numeric check(value > 0),
    frequency varchar check(frequency in ('one-off','daily','weekly','monthly')),
    foreign key (user_id) references users (user_id) 
);

create table one_offs (
    one_off_id serial primary key,
    expenditure_id int,
    occur_date date,
    foreign key (expenditure_id) references expenditures(expenditure_id) on delete cascade
);

create table dailys (
    daily_id serial primary key,
    expenditure_id int,
    start_date date,
    end_date date,
    foreign key (expenditure_id) references expenditures(expenditure_id) on delete cascade
);
    
create table weeklys (
    weekly_id serial primary key,
    expenditure_id int,
    start_week int check (start_week_number > 0 and start_week_number <= 53),
    start_year int check (start_year_number >= 2026 and start_year_number <= 2030),
    cycles int check (cycles > 0),
    foreign key (expenditure_id) references expenditures(expenditure_id) on delete cascade
);

create table weekly_days (
    weekly_id int,
    week_day int check (week_day >= 0 and week_day <= 7),
    foreign key (weekly_id) references weeklys(weekly_id) on delete cascade,
    primary key (weekly_id, week_day)
);

create table monthlys (
    monthly_id serial primary key,
    expenditure_id int,
    start_month int check (start_month_number >= 1 and start_month_number <= 12),
    start_year int check (start_year_number >= 2026 and start_year_number <= 2030),
    cycles int check (cycles > 0),
    foreign key (expenditure_id) references expenditures(expenditure_id) on delete cascade
);


create table monthly_days (
    monthly_id int,
    month_day int check (month_day >= 1 and month_day <= 31),
    foreign key (monthly_id) references monthlys(monthly_id) on delete cascade,
    primary key (monthly_id,month_day)
);

