# Optivio Rust/C++ message bridge

> **Quick take:** This is the small, deliberately boring wire contract between Optivio’s native components. Boring here means predictable, versioned, and easy to reject when something looks wrong.

> *“The fastest message is still a bad message if it cannot be validated.”*

The hot path uses a versioned fixed-layout frame. The bridge is intentionally separate from Python and Groq. Frames are little-endian and contain no pointers. Any unknown version, invalid length, NaN, stale timestamp, or sequence gap is rejected and increments a safety counter.

| Field | Type | Meaning |
|---|---:|---|
| magic | u32 | `0x4F505456` (`OPTV`) |
| version | u16 | Protocol version, currently `1` |
| kind | u16 | Quote, order intent, risk result, fill, or heartbeat |
| sequence | u64 | Monotonic stream sequence |
| timestamp_ns | u64 | Event timestamp |
| payload_len | u32 | Fixed payload byte length |
| flags | u32 | Validated status flags |

The Rust side owns risk-policy validation and returns allow/deny plus a reason code. The C++ side owns quote normalization and route scoring. Both sides must use the same schema test vectors. Python communicates through a local bounded IPC/FFI boundary and remains responsible for research and orchestration, not unchecked hot-path mutation.

The bridge must be upgraded to authenticated local IPC, bounded queues, backpressure behavior, restart recovery, sequence replay, and schema compatibility tests before a live paper process is trusted. A high-speed bridge does not make an invalid risk decision safe.
