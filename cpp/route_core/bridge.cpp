#include "bridge.hpp"

namespace optivio {
namespace {
void put16(std::vector<std::uint8_t>& out, std::uint16_t v) { out.push_back(static_cast<std::uint8_t>(v)); out.push_back(static_cast<std::uint8_t>(v >> 8)); }
void put32(std::vector<std::uint8_t>& out, std::uint32_t v) { for (int i = 0; i < 4; ++i) out.push_back(static_cast<std::uint8_t>(v >> (8 * i))); }
void put64(std::vector<std::uint8_t>& out, std::uint64_t v) { for (int i = 0; i < 8; ++i) out.push_back(static_cast<std::uint8_t>(v >> (8 * i))); }
std::uint16_t get16(const std::uint8_t* p) { return static_cast<std::uint16_t>(p[0]) | static_cast<std::uint16_t>(p[1] << 8); }
std::uint32_t get32(const std::uint8_t* p) { std::uint32_t v = 0; for (int i = 0; i < 4; ++i) v |= static_cast<std::uint32_t>(p[i]) << (8 * i); return v; }
std::uint64_t get64(const std::uint8_t* p) { std::uint64_t v = 0; for (int i = 0; i < 8; ++i) v |= static_cast<std::uint64_t>(p[i]) << (8 * i); return v; }
}

std::vector<std::uint8_t> encode(const FrameHeader& h, const std::vector<std::uint8_t>& payload) {
    // The wire field is 32-bit; refuse a payload the field cannot represent instead
    // of silently truncating the length (a 32-bit length-wrap).
    if (payload.size() != h.payload_len || payload.size() > UINT32_MAX) return {};
    std::vector<std::uint8_t> out; out.reserve(32 + payload.size());
    put32(out, kMagic); put16(out, kVersion); put16(out, h.kind); put64(out, h.sequence); put64(out, h.timestamp_ns); put32(out, h.payload_len); put32(out, h.flags);
    out.insert(out.end(), payload.begin(), payload.end()); return out;
}

bool validate(const std::vector<std::uint8_t>& f, std::uint64_t previous, FrameHeader& out) noexcept {
    if (f.size() < 32 || get32(f.data()) != kMagic || get16(f.data() + 4) != kVersion) return false;
    out.kind = get16(f.data() + 6); out.sequence = get64(f.data() + 8); out.timestamp_ns = get64(f.data() + 16); out.payload_len = get32(f.data() + 24); out.flags = get32(f.data() + 28);
    // Guard: a 32-bit payload_len can encode at most UINT32_MAX bytes; reject a
    // claimed length that cannot be represented or that exceeds the actual frame
    // length. The addition happens in size_t (64-bit), so a 32-bit payload_len can
    // never wrap the buffer arithmetic.
    const std::size_t claimed_total = static_cast<std::size_t>(out.payload_len) + 32;
    if (claimed_total != f.size()) return false;
    return out.sequence > previous;
}
}
