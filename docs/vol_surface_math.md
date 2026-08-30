# Optivio Hive-Kronos volatility-surface hybrid: mathematical specification

> **Quick take:** Here is the math behind Optivio’s causal volatility-surface model. The notation is formal because the checks need to be precise, but the workflow is meant to read like a guided tour.

> *“A surface is a collection of relationships that must remain believable together.”*

Let a decision timestamp be \(t\). For underlying \(a\), tenor bucket \(\tau\), and normalized log-moneyness \(k=\log(K/F_{a,t,\tau})\), the observable surface tensor is
\[
X_t^{(a)}(\tau,k) = [\mathrm{IV},\ \Delta\mathrm{IV},\ \mathrm{volume},\ \mathrm{spread},\ \mathrm{OI},\ \mathrm{RV},\ \mathrm{return},\ \mathrm{quality}],
\]
where every component satisfies \(\mathrm{available\_at}\le t\). Missing nodes have an explicit mask and are never forward-filled from future observations.

For a lookback \(L\), the input is \(X_{t-L+1:t}\in\mathbb{R}^{A\times L\times D}\). Training-fold-only robust bounds \(q^-_d,q^+_d\) map each channel to a clipped scalar \(z_{d}=\operatorname{clip}((x_d-q^-_d)/(q^+_d-q^-_d),0,1)\). Kronos-style hierarchical tokens are
\[
 c_d=\lfloor B_c z_d\rfloor,\qquad f_d=\lfloor B_f z_d\rfloor,
\]
with fixed \(B_c,B_f\) after fitting. Token summaries \(u_{a,\ell}=[\operatorname{mean}_d c_d/B_c,\operatorname{mean}_d f_d/B_f]\) are concatenated to the continuous feature vector.

For each asset node \(a\), the Hive-style hidden state evolves as
\[
 m_{a,\ell}=\frac{1}{|\mathcal N(a)|}\sum_{b\in\mathcal N(a)}h_{b,\ell-1},
\]
\[
 h_{a,\ell}=(1-\alpha)h_{a,\ell-1}+\alpha\tanh(W_x[x_{a,\ell};u_{a,\ell}]+W_hh_{a,\ell-1}+W_mm_{a,\ell-1}+b).
\]
The graph \(\mathcal N(a)\) is frozen before evaluation and may represent sector, index, correlation, or surface-node adjacency. It cannot be recomputed with future data during a test fold.

A cross-sectional representation is \(e_a=\operatorname{LayerNorm}(h_{a,L})\). The model uses four options heads:
\[
 \hat y_a^{dir}=\tanh(w_d^Te_a+b_d),\quad
 \hat y_a^{move}=\operatorname{softplus}(w_m^Te_a+b_m),
\]
\[
 \hat y_a^{vol}=\operatorname{softplus}(w_v^Te_a+b_v)+\epsilon,\quad
 \hat y_a^{liq}=\sigma(w_l^Te_a+b_l).
\]
Production surface heads should add \(\widehat{\Delta IV}_{ATM}\), risk-reversal slope, butterfly curvature, term-structure slope, node residual, fill probability, and expected implementation cost.

A cost-aware training objective is
\[
 \mathcal L = \lambda_d\ell_{Huber}(y^{dir},\hat y^{dir})
 +\lambda_m\ell_{Huber}(y^{move},\hat y^{move})
 +\lambda_v\ell_{Huber}(y^{vol},\hat y^{vol})
 +\lambda_l\ell_{BCE}(y^{liq},\hat y^{liq})
 +\lambda_s\|\nabla_k\hat{IV}-\nabla_k IV\|_1
 +\lambda_c\,\mathrm{turnover}
 +\lambda_r\,\mathrm{drawdown\_proxy}.
\]
The surface term penalizes inaccurate skew/curvature dynamics; turnover and drawdown terms prevent a high-return but untradeable signal from dominating.

The paper-trading decision is a deterministic function
\[
 a_t = \mathcal R(\mathcal G(\mathcal P(\mathcal S(\hat y_t, r_t)))),
\]
where \(\mathcal S\) is signal aggregation, \(\mathcal P\) portfolio sizing, \(\mathcal G\) Greeks/risk gating, and \(\mathcal R\) quote-aware routing. The LLM is not in this function. All model feedback from realized PnL is delayed until the outcome is observable and is recorded with an `available_at` timestamp; it cannot revise a historical feature or decision.

Zero-shot evaluation freezes token bounds, graph, weights, hyperparameters, strategy parameters, and feedback cutoffs. The final test block is not used by evolutionary search, calibration, model selection, or post-hoc feature engineering.
