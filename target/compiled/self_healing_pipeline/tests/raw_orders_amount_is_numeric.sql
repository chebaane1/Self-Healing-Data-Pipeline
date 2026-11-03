select
    order_id,
    amount
from "pipeline"."main"."raw_orders"
where amount is not null
  and try_cast(amount as float) is null