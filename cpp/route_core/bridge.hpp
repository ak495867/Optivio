#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace optivio {
constexpr std::uint32_t kMagic = 0x4F505456;
constexpr std::uint16_t kVersion = 1;
struct FrameHeader { std::uint16_t kind; std::uint64_t sequence; std::uint64_t timestamp_ns; std::uint32_t payload_len; std::uint32_t flags; };
std::vector<std::uint8_t> encode(const FrameHeader& header, const std::vector<std::uint8_t>& payload);
bool validate(const std::vector<std::uint8_t>& frame, std::uint64_t previous_sequence, FrameHeader& out) noexcept;
}
