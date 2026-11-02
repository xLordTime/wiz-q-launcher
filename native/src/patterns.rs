// Pure pattern validation; no process access. Derived from the Deimos login
// instruction sequence and wizwalker's RootWindowHook (see PROVENANCE.md).

#[derive(Debug, PartialEq, Eq)]
pub enum PatternError {
    Missing,
    Ambiguous,
}

#[derive(Debug, PartialEq, Eq)]
pub struct LoginSite {
    pub dat_offset: usize,
    pub function_offset: usize,
}

fn unique<T>(mut matches: impl Iterator<Item = T>) -> Result<T, PatternError> {
    let first = matches.next().ok_or(PatternError::Missing)?;
    if matches.next().is_some() {
        return Err(PatternError::Ambiguous);
    }
    Ok(first)
}

fn relative_target(data: &[u8], at: usize) -> Option<usize> {
    let displacement = i32::from_le_bytes(data.get(at..at + 4)?.try_into().ok()?);
    let target = (at as i64 + 4).checked_add(displacement as i64)?;
    (target >= 0 && target < data.len() as i64).then_some(target as usize)
}

/// Match the same dispatcher call as Deimos. Only the stack-local displacement
/// is variable; verify mov rcx,[rip+disp32], the E8 call and both module targets.
/// EU/US compiler layouts can use either an 8-bit or 32-bit stack displacement.
pub fn login_site(data: &[u8]) -> Result<LoginSite, PatternError> {
    const PREFIX: &[u8] = &[0x41, 0xB1, 0x01, 0x45, 0x33, 0xC0, 0x48, 0x8D];
    unique(data.windows(PREFIX.len()).enumerate().filter_map(|(offset, bytes)| {
        if bytes != PREFIX {
            return None;
        }
        let mov = match data.get(offset + 8)? {
            0x55 => offset + 10,
            0x95 => offset + 13,
            _ => return None,
        };
        if data.get(mov..mov + 3)? != [0x48, 0x8B, 0x0D] || *data.get(mov + 7)? != 0xE8 {
            return None;
        }
        let dat_offset = relative_target(data, mov + 3)?;
        let function_offset = relative_target(data, mov + 8)?;
        data.get(dat_offset..dat_offset + 8)?;
        Some(LoginSite { dat_offset, function_offset })
    }))
}

/// RootWindowHook begins with mov rcx,[r15+disp32]. The old seven wildcards
/// also matched unrelated instruction boundaries. Keep the root-member offset
/// variable, but require the actual instruction and the Deimos suffix.
pub fn hook_site(data: &[u8]) -> Result<usize, PatternError> {
    unique(data.windows(21).enumerate().filter_map(|(offset, bytes)| {
        (bytes[..3] == [0x49, 0x8B, 0x8F]
            && bytes[7..10] == [0x48, 0x8B, 0x01]
            && bytes[17..21] == [0xFF, 0x50, 0x70, 0x84])
            .then_some(offset)
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dispatcher(data: &mut [u8], offset: usize, wide: bool, displacement: u8) {
        let prefix = [0x41, 0xB1, 0x01, 0x45, 0x33, 0xC0, 0x48, 0x8D];
        data[offset..offset + 8].copy_from_slice(&prefix);
        data[offset + 8] = if wide { 0x95 } else { 0x55 };
        data[offset + 9] = displacement;
        let mov = offset + if wide { 13 } else { 10 };
        data[mov..mov + 3].copy_from_slice(&[0x48, 0x8B, 0x0D]);
        data[mov + 3..mov + 7].copy_from_slice(&(200i32 - (mov as i32 + 7)).to_le_bytes());
        data[mov + 7] = 0xE8;
        data[mov + 8..mov + 12].copy_from_slice(&(220i32 - (mov as i32 + 12)).to_le_bytes());
    }

    #[test]
    fn dispatcher_accepts_stack_layouts_and_preserves_relative_targets() {
        for wide in [false, true] {
            for displacement in [0xCF, 0xD7, 0xA8] {
                let mut data = vec![0; 256];
                dispatcher(&mut data, 32, wide, displacement);
                assert_eq!(login_site(&data), Ok(LoginSite { dat_offset: 200, function_offset: 220 }));
            }
        }
    }

    #[test]
    fn dispatcher_rejects_false_matches_bad_targets_and_ambiguity() {
        let mut data = vec![0; 256];
        dispatcher(&mut data, 32, false, 0xCF);
        data[49] = 0x90; // not a call
        assert_eq!(login_site(&data), Err(PatternError::Missing));
        dispatcher(&mut data, 32, false, 0xCF);
        data[45..49].copy_from_slice(&i32::MAX.to_le_bytes());
        assert_eq!(login_site(&data), Err(PatternError::Missing));
        dispatcher(&mut data, 32, false, 0xCF);
        dispatcher(&mut data, 80, true, 0xA8);
        assert_eq!(login_site(&data), Err(PatternError::Ambiguous));
    }

    #[test]
    fn hook_rejects_old_wildcard_false_positive_and_keeps_unique_root_instruction() {
        let mut data = vec![0; 128];
        data[7..10].copy_from_slice(&[0x48, 0x8B, 0x01]);
        data[17..21].copy_from_slice(&[0xFF, 0x50, 0x70, 0x84]);
        assert_eq!(hook_site(&data), Err(PatternError::Missing));
        let root = [0x49, 0x8B, 0x8F, 0xD8, 0, 0, 0, 0x48, 0x8B, 0x01, 0, 0, 0, 0, 0, 0, 0, 0xFF, 0x50, 0x70, 0x84];
        data[32..53].copy_from_slice(&root);
        assert_eq!(hook_site(&data), Ok(32));
        data[64..85].copy_from_slice(&root);
        assert_eq!(hook_site(&data), Err(PatternError::Ambiguous));
    }

    #[test]
    fn truncated_data_is_rejected_without_panicking() {
        for length in 0..32 {
            let data = vec![0x41; length];
            assert_eq!(login_site(&data), Err(PatternError::Missing));
            assert_eq!(hook_site(&data), Err(PatternError::Missing));
        }
    }
}
