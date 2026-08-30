(* Add this to the top of test_policy.ml *)
open Optivio_policy.Policy

let test_validate_paper_mode () =
  (* Now 'validate' and the record type are in scope *)
  match validate { paper_mode=true; kill_switch=false; max_order_notional=100.; model_approved=true } with
  | Ok _ -> true
  | Error _ -> false
open Optivio_policy
let () =
  match validate { paper_mode=true; kill_switch=false; max_order_notional=100.; model_approved=true } with
  | Allow -> ()
  | Deny _ -> exit 1
