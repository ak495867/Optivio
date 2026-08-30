#![forbid(unsafe_code)]

pub mod bridge;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateError { KillSwitch, InvalidNotional, OrderLimit, PortfolioLimit, DailyLoss }

#[derive(Debug, Clone, Copy)]
pub struct RiskSnapshot { pub equity: f64, pub open_notional: f64, pub daily_loss: f64, pub kill_switch: bool }

#[derive(Debug, Clone, Copy)]
pub struct RiskLimits { pub max_order_notional: f64, pub max_open_notional: f64, pub max_daily_loss_fraction: f64 }

pub fn approve(snapshot: RiskSnapshot, limits: RiskLimits, order_notional: f64) -> Result<(), GateError> {
    if snapshot.kill_switch { return Err(GateError::KillSwitch); }
    if !order_notional.is_finite() || order_notional <= 0.0 { return Err(GateError::InvalidNotional); }
    if order_notional > limits.max_order_notional { return Err(GateError::OrderLimit); }
    if snapshot.open_notional + order_notional > limits.max_open_notional { return Err(GateError::PortfolioLimit); }
    if snapshot.daily_loss > snapshot.equity * limits.max_daily_loss_fraction { return Err(GateError::DailyLoss); }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_kill_switch() {
        let s = RiskSnapshot { equity: 10000.0, open_notional: 0.0, daily_loss: 0.0, kill_switch: true };
        let l = RiskLimits { max_order_notional: 1000.0, max_open_notional: 5000.0, max_daily_loss_fraction: 0.02 };
        assert_eq!(approve(s, l, 100.0), Err(GateError::KillSwitch));
    }
}
