#pragma once
#include <cstdint>
#include <cstddef>
#include <optional>
#include <string_view>

namespace optivio {
struct Quote { double bid; double ask; std::uint32_t bid_size; std::uint32_t ask_size; };
struct Route { double price; double score; };
std::optional<Route> choose(const Quote* quotes, std::size_t count, bool buy, std::uint32_t quantity) noexcept;
}
