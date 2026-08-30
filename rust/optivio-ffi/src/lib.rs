//! C-ABI exports for the Optivio risk gate.
//!
//! This crate is the thin `cdylib` that a Python `ctypes` (or other C ABI) caller
//! loads. The decision logic lives entirely in `optivio-risk`, which is
//! `#![forbid(unsafe_code)]`; only the pointer-marshaling ABI lives here. The
//! wire contract is versioned (`optivio_gate_approve_v1`).

use core::ffi::{c_char, c_double, c_int, c_uint};

use optivio_risk::{approve, GateError, RiskLimits, RiskSnapshot};

/// C-compatible mirror of `RiskLimits`.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct CRiskLimits {
    pub max_order_notional: c_double,
    pub max_open_notional: c_double,
    pub max_daily_loss_fraction: c_double,
}

/// C-compatible mirror of `RiskSnapshot`.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct CRiskSnapshot {
    pub equity: c_double,
    pub open_notional: c_double,
    pub daily_loss: c_double,
    pub kill_switch: c_int,
}

pub const GATE_OK: c_int = 0;
pub const GATE_KILL_SWITCH: c_int = 1;
pub const GATE_INVALID_NOTIONAL: c_int = 2;
pub const GATE_ORDER_LIMIT: c_int = 3;
pub const GATE_PORTFOLIO_LIMIT: c_int = 4;
pub const GATE_DAILY_LOSS: c_int = 5;

/// Approve one order against a set of limits. Returns a `GATE_*` code.
///
/// # Safety
/// `reason_out` must point to a writable buffer of at least `reason_cap` bytes, or
/// be null to skip writing the reason.
#[no_mangle]
pub unsafe extern "C" fn optivio_gate_approve_v1(
    limits: CRiskLimits,
    snapshot: CRiskSnapshot,
    order_notional: c_double,
    reason_out: *mut c_char,
    reason_cap: c_uint,
) -> c_int {
    let limits_rust = RiskLimits {
        max_order_notional: limits.max_order_notional,
        max_open_notional: limits.max_open_notional,
        max_daily_loss_fraction: limits.max_daily_loss_fraction,
    };
    let snapshot_rust = RiskSnapshot {
        equity: snapshot.equity,
        open_notional: snapshot.open_notional,
        daily_loss: snapshot.daily_loss,
        kill_switch: snapshot.kill_switch != 0,
    };
    let result = approve(snapshot_rust, limits_rust, order_notional);
    let (code, message) = match result {
        Ok(()) => (GATE_OK, "approved"),
        Err(GateError::KillSwitch) => (GATE_KILL_SWITCH, "kill switch is active"),
        Err(GateError::InvalidNotional) => (GATE_INVALID_NOTIONAL, "invalid notional"),
        Err(GateError::OrderLimit) => (GATE_ORDER_LIMIT, "order limit exceeded"),
        Err(GateError::PortfolioLimit) => (GATE_PORTFOLIO_LIMIT, "portfolio limit exceeded"),
        Err(GateError::DailyLoss) => (GATE_DAILY_LOSS, "daily loss limit exceeded"),
    };
    if !reason_out.is_null() && reason_cap > 0 {
        let bytes = message.as_bytes();
        let n = bytes.len().min((reason_cap - 1) as usize);
        for (i, b) in bytes.iter().take(n).enumerate() {
            unsafe { *reason_out.add(i) = *b as c_char };
        }
        unsafe { *reason_out.add(n) = 0 };
    }
    code
}