open Optivio_policy.Policy

(* Helper to assert that a config results in Allow *)
let assert_allow msg config =
  match validate config with
  | Allow -> 
      print_endline ("[PASS] " ^ msg)
  | Deny reason -> 
      print_endline ("[FAIL] " ^ msg ^ " - Expected Allow, got Deny: " ^ reason);
      exit 1

(* Helper to assert that a config results in Deny *)
let assert_deny msg config =
  match validate config with
  | Deny _ -> 
      print_endline ("[PASS] " ^ msg)
  | Allow -> 
      print_endline ("[FAIL] " ^ msg ^ " - Expected Deny, got Allow");
      exit 1

let () =
  (* Test 1: Valid config (should Allow) *)
  assert_allow "Valid config allows trade" 
    { paper_mode=true; kill_switch=false; max_order_notional=100.; model_approved=true };

  (* Test 2: Paper mode false (should Deny) *)
  assert_deny "Paper mode false denies trade" 
    { paper_mode=false; kill_switch=false; max_order_notional=100.; model_approved=true };

  (* Test 3: Kill switch active (should Deny) *)
  assert_deny "Kill switch active denies trade" 
    { paper_mode=true; kill_switch=true; max_order_notional=100.; model_approved=true };

  (* Test 4: Invalid order limit / negative (should Deny) *)
  assert_deny "Invalid order limit denies trade" 
    { paper_mode=true; kill_switch=false; max_order_notional=(-10.); model_approved=true };

  (* Test 5: Model not approved (should Deny) *)
  assert_deny "Model not approved denies trade" 
    { paper_mode=true; kill_switch=false; max_order_notional=100.; model_approved=false };

  print_endline "\nAll tests passed successfully!"