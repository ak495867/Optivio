open Optivio_policy
let () =
  match validate { paper_mode=true; kill_switch=false; max_order_notional=100.; model_approved=true } with
  | Allow -> ()
  | Deny _ -> exit 1
