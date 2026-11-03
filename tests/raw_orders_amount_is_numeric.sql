select
    order_id,
    amount
from {{ source('raw', 'orders') }}
where amount is not null
  and try_cast(amount as float) is null