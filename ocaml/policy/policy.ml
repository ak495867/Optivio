type decision =
  | Allow
  | Deny of string

type config = {
  paper_mode: bool;
  kill_switch: bool;
  max_order_notional: float;
  model_approved: bool
}

type order = {
  quantity: int;         (* number of contracts *)
  price: float;          (* per-contract price *)
}

(* Order size in notional terms: quantity * price * contract multiplier (100). *)
let order_notional o =
  Float.of_int o.quantity *. o.price *. 100.

let validate_config c =
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

(* Config-only entry point kept for callers of the original `validate`. *)
let validate = validate_config

(* Validate a concrete order against config. Compares the actual order size
   (notional) against the configured max_order_notional. *)
let validate_order c o =
  if not (Float.is_finite o.price) || o.price <= 0. then
    Deny "order price must be finite and positive"
  else if o.quantity <= 0 then
    Deny "order size must be positive"
  else if order_notional o > c.max_order_notional then
    Deny "order size exceeds configured notional limit"
  else
    validate_config c