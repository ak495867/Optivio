#include "route_core.hpp"
#include <algorithm>
#include <cmath>
namespace optivio {
std::optional<Route> choose(const Quote* quotes, std::size_t count, bool buy, std::uint32_t quantity) noexcept {
    std::optional<Route> best;
    for (std::size_t i = 0; i < count; ++i) {
        const auto& q = quotes[i];
        if (std::min(q.bid_size, q.ask_size) < quantity || q.bid < 0 || q.ask < q.bid) continue;
        const double mid = (q.bid + q.ask) * 0.5;
        if (!std::isfinite(mid) || mid <= 0) continue;
        const double price = buy ? q.ask : q.bid;
        const double score = -((q.ask - q.bid) / mid) - (1.0 / std::max<std::uint32_t>(1, std::min(q.bid_size, q.ask_size)));
        if (!best || score > best->score) best = Route{price, score};
    }
    return best;
}
}
