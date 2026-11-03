
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select
    order_id,
    amount
from "pipeline"."main"."raw_orders"
where amount is not null
  and try_cast(amount as float) is null
  
  
      
    ) dbt_internal_test