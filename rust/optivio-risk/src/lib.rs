#![forbid(unsafe_code)]

pub mod bridge;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateError {
    KillSwitch,
    InvalidNotional,
    OrderLimit,
    PortfolioLimit,
    DailyLoss,
}

#[derive(Debug, Clone, Copy)]
pub struct RiskSnapshot {
    pub equity: f64,
    pub open_notional: f64,
    pub daily_loss: f64,
    pub kill_switch: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct RiskLimits {
    pub max_order_notional: f64,
    pub max_open_notional: f64,
    pub max_daily_loss_fraction: f64,
}

pub fn approve(
    snapshot: RiskSnapshot,
    limits: RiskLimits,
    order_notional: f64,
) -> Result<(), GateError> {
    if snapshot.kill_switch {
        return Err(GateError::KillSwitch);
    }
    if !order_notional.is_finite() || order_notional <= 0.0 {
        return Err(GateError::InvalidNotional);
    }
    // Fail closed on any non-finite input: NaN comparisons are all false, so a NaN
    // equity/open_notional/daily_loss (or a NaN limit) must reject the order rather
    // than silently pass every bound.
    if !snapshot.equity.is_finite()
        || !snapshot.open_notional.is_finite()
        || !snapshot.daily_loss.is_finite()
        || !limits.max_order_notional.is_finite()
        || !limits.max_open_notional.is_finite()
        || !limits.max_daily_loss_fraction.is_finite()
    {
        return Err(GateError::InvalidNotional);
    }
    if order_notional > limits.max_order_notional {
        return Err(GateError::OrderLimit);
    }
    if snapshot.open_notional + order_notional > limits.max_open_notional {
        return Err(GateError::PortfolioLimit);
    }
    if snapshot.daily_loss > snapshot.equity * limits.max_daily_loss_fraction {
        return Err(GateError::DailyLoss);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_kill_switch() {
        let s = RiskSnapshot {
            equity: 10000.0,
            open_notional: 0.0,
            daily_loss: 0.0,
            kill_switch: true,
        };
        let l = RiskLimits {
            max_order_notional: 1000.0,
            max_open_notional: 5000.0,
            max_daily_loss_fraction: 0.02,
        };
        assert_eq!(approve(s, l, 100.0), Err(GateError::KillSwitch));
    }

    #[test]
    fn rejects_nan_daily_loss_fail_closed() {
        let s = RiskSnapshot {
            equity: 10000.0,
            open_notional: 0.0,
            daily_loss: f64::NAN,
            kill_switch: false,
        };
        let l = RiskLimits {
            max_order_notional: 1000.0,
            max_open_notional: 5000.0,
            max_daily_loss_fraction: 0.02,
        };
        // NaN daily_loss must REJECT, not silently pass the daily-loss bound.
        assert_eq!(approve(s, l, 100.0), Err(GateError::InvalidNotional));
    }

    #[test]
    fn rejects_nan_equity_fail_closed() {
        let s = RiskSnapshot {
            equity: f64::NAN,
            open_notional: 0.0,
            daily_loss: 0.0,
            kill_switch: false,
        };
        let l = RiskLimits {
            max_order_notional: 1000.0,
            max_open_notional: 5000.0,
            max_daily_loss_fraction: 0.02,
        };
        assert_eq!(approve(s, l, 100.0), Err(GateError::InvalidNotional));
    }
}
