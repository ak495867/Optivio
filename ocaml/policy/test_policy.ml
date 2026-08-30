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

(* Helper to assert that an order is allowed against a config *)
let assert_order_allow msg config order =
  match validate_order config order with
  | Allow ->
      print_endline ("[PASS] " ^ msg)
  | Deny reason ->
      print_endline ("[FAIL] " ^ msg ^ " - Expected Allow, got Deny: " ^ reason);
      exit 1

(* Helper to assert that an order is denied and the denial mentions the cause *)
let assert_order_deny msg config order =
  match validate_order config order with
  | Deny _ ->
      print_endline ("[PASS] " ^ msg)
  | Allow ->
      print_endline ("[FAIL] " ^ msg ^ " - Expected Deny, got Allow");
      exit 1

let valid_config = { paper_mode=true; kill_switch=false; max_order_notional=10000.; model_approved=true }

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

  (* Test 6: Order under the notional limit (should Allow) *)
  assert_order_allow "Order under notional limit allows trade" valid_config
    { quantity=50; price=1.5 };

  (* Test 7: Order notional exactly at the limit (should Allow) *)
  assert_order_allow "Order exactly at notional limit allows trade" valid_config
    { quantity=100; price=1. };

  (* Test 8: Order notional above the limit (should Deny) *)
  assert_order_deny "Order above notional limit denies trade" valid_config
    { quantity=1; price=10001. };

  (* Test 9: Zero quantity (should Deny) *)
  assert_order_deny "Zero quantity denies trade" valid_config
    { quantity=0; price=1.; };

  (* Test 10: Negative quantity (should Deny) *)
  assert_order_deny "Negative quantity denies trade" valid_config
    { quantity=(-1); price=1.; };

  (* Test 11: Non-finite price (should Deny) *)
  assert_order_deny "Non-finite price denies trade" valid_config
    { quantity=1; price=Float.nan };

  print_endline "\nAll tests passed successfully!"