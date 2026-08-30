#include "route_core.hpp"
#include <cassert>
int main() {
    const optivio::Quote quotes[] = {{1.0, 1.2, 10, 10}, {1.0, 1.1, 10, 10}};
    auto route = optivio::choose(quotes, 2, true, 1);
    assert(route.has_value() && route->price == 1.1);
    return 0;
}
