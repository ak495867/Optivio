#include "bridge.hpp"
#include <cassert>

int main() {
    const optivio::FrameHeader header{2, 10, 123456, 3, 0};
    const std::vector<std::uint8_t> payload{1, 2, 3};
    const auto frame = optivio::encode(header, payload);
    optivio::FrameHeader decoded{};
    assert(!frame.empty() && optivio::validate(frame, 9, decoded));
    assert(decoded.kind == 2 && decoded.sequence == 10 && decoded.payload_len == 3);
    assert(!optivio::validate(frame, 10, decoded));
    return 0;
}
