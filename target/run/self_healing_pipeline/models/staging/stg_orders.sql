
    

    create  table
      "pipeline"."main"."stg_orders__dbt_tmp"
  
    
    as (
      select
    order_id,
    customer_id,
    case 
        when total_amount = 'INVALID' then null
        else try_cast(total_amount as double)
    end as amount,
    order_date
from "pipeline"."main"."raw_orders"
    );
    
  