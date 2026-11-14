select
    order_id,
    customer_id,
    case 
        when total_amount = 'INVALID' then null
        else try_cast(total_amount as double)
    end as total_amount,
    order_date
from {{ source('raw', 'orders') }}
