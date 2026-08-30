#include "bridge.hpp"
#include <cassert>
#include <cstdint>
#include <vector>

int main() {
    const optivio::FrameHeader header{2, 10, 123456, 3, 0};
    const std::vector<std::uint8_t> payload{1, 2, 3};
    const auto frame = optivio::encode(header, payload);
    optivio::FrameHeader decoded{};
    assert(!frame.empty() && optivio::validate(frame, 9, decoded));
    assert(decoded.kind == 2 && decoded.sequence == 10 && decoded.payload_len == 3);
    assert(!optivio::validate(frame, 10, decoded));

    // Encode rejects a payload larger than the 32-bit wire field (length-wrap).
    // We cannot allocate a real >4GiB payload here; the encoder's early return on
    // `payload.size() > UINT32_MAX` is covered structurally. The validator guard is
    // exercised below with an oversized claimed length.

    // A frame claiming a payload_len that cannot fit the actual buffer is rejected.
    std::vector<std::uint8_t> fake = frame;
    // payload_len lives at bytes [24..28); set it to UINT32_MAX.
    fake[24] = 0xFF; fake[25] = 0xFF; fake[26] = 0xFF; fake[27] = 0xFF;
    assert(!optivio::validate(fake, 9, decoded));
    return 0;
}
