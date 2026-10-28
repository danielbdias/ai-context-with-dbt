select
    dateadd(day, row_number() over (order by seq4()) - 1, '2024-01-01'::date) as date_day
from table(generator(rowcount => 3650))
