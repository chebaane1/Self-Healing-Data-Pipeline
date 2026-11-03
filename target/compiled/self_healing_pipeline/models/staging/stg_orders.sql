select
    order_id,
    customer_id,
    cast(amount as float) as amount,
    order_date
from "pipeline"."main"."raw_orders"