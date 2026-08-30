#![forbid(unsafe_code)]

pub const MAGIC: u32 = 0x4F50_5456;
pub const VERSION: u16 = 1;
pub const HEADER_LEN: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameError { TooShort, BadMagic, BadVersion, BadLength, NonMonotonicSequence }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Header { pub kind: u16, pub sequence: u64, pub timestamp_ns: u64, pub payload_len: u32, pub flags: u32 }

pub fn encode(header: Header, payload: &[u8]) -> Result<Vec<u8>, FrameError> {
    if payload.len() != header.payload_len as usize { return Err(FrameError::BadLength); }
    let mut out = Vec::with_capacity(HEADER_LEN + payload.len());
    out.extend_from_slice(&MAGIC.to_le_bytes());
    out.extend_from_slice(&VERSION.to_le_bytes());
    out.extend_from_slice(&header.kind.to_le_bytes());
    out.extend_from_slice(&header.sequence.to_le_bytes());
    out.extend_from_slice(&header.timestamp_ns.to_le_bytes());
    out.extend_from_slice(&header.payload_len.to_le_bytes());
    out.extend_from_slice(&header.flags.to_le_bytes());
    out.extend_from_slice(payload);
    Ok(out)
}

pub fn validate(frame: &[u8], previous_sequence: Option<u64>) -> Result<Header, FrameError> {
    if frame.len() < HEADER_LEN { return Err(FrameError::TooShort); }
    let magic = u32::from_le_bytes(frame[0..4].try_into().map_err(|_| FrameError::TooShort)?);
    let version = u16::from_le_bytes(frame[4..6].try_into().map_err(|_| FrameError::TooShort)?);
    let kind = u16::from_le_bytes(frame[6..8].try_into().map_err(|_| FrameError::TooShort)?);
    let sequence = u64::from_le_bytes(frame[8..16].try_into().map_err(|_| FrameError::TooShort)?);
    let timestamp_ns = u64::from_le_bytes(frame[16..24].try_into().map_err(|_| FrameError::TooShort)?);
    let payload_len = u32::from_le_bytes(frame[24..28].try_into().map_err(|_| FrameError::TooShort)?);
    let flags = u32::from_le_bytes(frame[28..32].try_into().map_err(|_| FrameError::TooShort)?);
    if magic != MAGIC { return Err(FrameError::BadMagic); }
    if version != VERSION { return Err(FrameError::BadVersion); }
    if frame.len() != HEADER_LEN + payload_len as usize { return Err(FrameError::BadLength); }
    if previous_sequence.is_some_and(|previous| sequence <= previous) { return Err(FrameError::NonMonotonicSequence); }
    Ok(Header { kind, sequence, timestamp_ns, payload_len, flags })
}
