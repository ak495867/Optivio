type decision = 
  | Allow 
  | Deny of string

type config = { 
  paper_mode: bool; 
  kill_switch: bool; 
  max_order_notional: float; 
  model_approved: bool 
}

let validate c =
  if not c.paper_mode then 
    Deny "paper_mode must be true"
  else if c.kill_switch then 
    Deny "kill switch is active"
  else if not (Float.is_finite c.max_order_notional) || c.max_order_notional <= 0. then 
    Deny "invalid order limit"
  else if not c.model_approved then 
    Deny "model is not approved"
  else 
    Allow