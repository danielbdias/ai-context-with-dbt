{{ config(materialized='table', order_by='date_day') }}

select toDate('2024-01-01') + number as date_day
from numbers(3650)
