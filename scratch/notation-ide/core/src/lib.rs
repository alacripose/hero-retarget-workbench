// The crudity classifier: the page writes UTF-8 into `crudity_input`, calls `crudity_analyse`, and reads rows back.
// The ladder is named, never scored: whole, annotated, lossy, shorthand.

#![allow(static_mut_refs)]

const CAPACITY: usize = 1 << 16;
const MAX_LINES: usize = 512;

pub const GAP_SHORT_STUB: u32 = 1;
pub const GAP_BOLD_LEAD_ONLY: u32 = 2;
pub const GAP_POINTER_INSTEAD: u32 = 4;
pub const GAP_NO_VERB: u32 = 8;
pub const GAP_SEMICOLON_DUMP: u32 = 16;
pub const GAP_UNEXPLAINED_NUMBER: u32 = 32;
pub const GAP_TRUNCATED: u32 = 64;
pub const GAP_NOUN_CHAIN: u32 = 128;

static mut INPUT: [u8; CAPACITY] = [0; CAPACITY];
static mut STARTS: [u32; MAX_LINES] = [0; MAX_LINES];
static mut LENS: [u32; MAX_LINES] = [0; MAX_LINES];
static mut WORDS: [u32; MAX_LINES] = [0; MAX_LINES];
static mut MASKS: [u32; MAX_LINES] = [0; MAX_LINES];
static mut GRADES: [u32; MAX_LINES] = [0; MAX_LINES];
static mut LINES: u32 = 0;

const VERBS: &[&str] = &[
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "does", "do", "did",
    "can", "could", "will", "would", "should", "must", "may", "might", "run", "runs", "read",
    "reads", "write", "writes", "call", "calls", "set", "sets", "clear", "clears", "draw",
    "draws", "show", "shows", "keep", "keeps", "need", "needs", "take", "takes", "give", "gives",
    "make", "makes", "open", "opens", "close", "closes", "dock", "docks", "move", "moves", "stop",
    "stops", "fail", "fails", "refuse", "refuses", "return", "returns", "hold", "holds", "end",
    "ends", "start", "starts", "reset", "resets", "sit", "sits", "work", "works", "use", "uses",
    "add", "adds", "remove", "removes", "check", "checks", "measure", "measures", "pass", "passes",
    "report", "reports", "live", "lives", "stay", "stays", "come", "comes", "go", "goes", "get",
    "gets", "land", "lands", "carry", "carries", "ship", "ships", "build", "builds", "mount",
    "mounts", "render", "renders", "parse", "parses", "decide", "decides", "name", "names",
    "mark", "marks", "ask", "asks", "answer", "answers", "record", "records", "apply", "applies",
    "count", "counts", "treat", "treats", "earn", "earns", "leave", "leaves", "lose", "loses",
];

const UNITS: &[&str] = &[
    "px", "ms", "s", "m", "%", "word", "words", "line", "lines", "byte", "bytes", "test", "tests",
    "section", "sections", "file", "files", "panel", "panels", "operator", "operators", "frame",
    "frames", "x=", "y=", "dt",
];

#[no_mangle]
pub extern "C" fn crudity_version() -> u32 {
    1
}

#[no_mangle]
pub extern "C" fn crudity_input() -> u32 {
    unsafe { INPUT.as_ptr() as u32 }
}

#[no_mangle]
pub extern "C" fn crudity_capacity() -> u32 {
    CAPACITY as u32
}

#[no_mangle]
pub extern "C" fn crudity_line_count() -> u32 {
    unsafe { LINES }
}

#[no_mangle]
pub extern "C" fn crudity_start(index: u32) -> u32 {
    if index >= MAX_LINES as u32 {
        return 0;
    }
    unsafe { STARTS[index as usize] }
}

#[no_mangle]
pub extern "C" fn crudity_len(index: u32) -> u32 {
    if index >= MAX_LINES as u32 {
        return 0;
    }
    unsafe { LENS[index as usize] }
}

#[no_mangle]
pub extern "C" fn crudity_words(index: u32) -> u32 {
    if index >= MAX_LINES as u32 {
        return 0;
    }
    unsafe { WORDS[index as usize] }
}

#[no_mangle]
pub extern "C" fn crudity_mask(index: u32) -> u32 {
    if index >= MAX_LINES as u32 {
        return 0;
    }
    unsafe { MASKS[index as usize] }
}

#[no_mangle]
pub extern "C" fn crudity_grade(index: u32) -> u32 {
    if index >= MAX_LINES as u32 {
        return 0;
    }
    unsafe { GRADES[index as usize] }
}

/// Read `len` bytes that the caller already wrote into `crudity_input`.
/// Returns the number of non-empty lines classified.
#[no_mangle]
pub extern "C" fn crudity_analyse(len: u32) -> u32 {
    let len = len as usize;
    if len > CAPACITY {
        return 0;
    }
    let text = unsafe { std::str::from_utf8(&INPUT[..len]) }.unwrap_or("");
    let mut count = 0usize;
    let mut offset = 0usize;
    for raw in text.split('\n') {
        let start = offset;
        offset += raw.len() + 1;
        let line = raw.trim_end_matches('\r').trim();
        if line.is_empty() || count >= MAX_LINES {
            continue;
        }
        let (mask, words) = classify(line);
        let grade = match mask.count_ones() {
            0 => 0,
            1 => 1,
            2 => 2,
            _ => 3,
        };
        unsafe {
            STARTS[count] = (start + (raw.len() - raw.trim_start().len())) as u32;
            LENS[count] = line.len() as u32;
            WORDS[count] = words;
            MASKS[count] = mask;
            GRADES[count] = grade;
        }
        count += 1;
    }
    unsafe { LINES = count as u32 };
    count as u32
}

fn lower_word(token: &str) -> String {
    token
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .collect::<String>()
        .to_ascii_lowercase()
}

fn classify(line: &str) -> (u32, u32) {
    let mut mask = 0u32;
    let tokens: Vec<&str> = line.split_whitespace().collect();
    let words = tokens.len() as u32;

    if words < 5 {
        mask |= GAP_SHORT_STUB;
    }

    // Trimming every '*' eats the opening marker, so the bullet is stripped first.
    let mut body = line.trim();
    for bullet in ["- ", "* ", "• "] {
        if let Some(rest) = body.strip_prefix(bullet) {
            body = rest.trim();
            break;
        }
    }
    let closing = body.strip_suffix('.').unwrap_or(body);
    if body.starts_with("**") && body.matches("**").count() == 2 && closing.ends_with("**") {
        mask |= GAP_BOLD_LEAD_ONLY;
    }

    let lower = line.to_ascii_lowercase();
    let pointer = ["docs/history", "see above", "as above", "see §", "as noted", "artifacts/agents-judge"]
        .iter()
        .any(|needle| lower.contains(needle))
        || lower.contains("row `");
    if pointer && words < 18 {
        mask |= GAP_POINTER_INSTEAD;
    }

    let has_verb = tokens.iter().any(|token| {
        let word = lower_word(token);
        VERBS.iter().any(|verb| verb == &word)
    });
    if !has_verb && !line.contains('`') && words >= 5 {
        mask |= GAP_NO_VERB;
    }

    if line.matches(';').count() >= 2 {
        mask |= GAP_SEMICOLON_DUMP;
    }

    let has_digit = tokens.iter().any(|token| token.chars().any(|c| c.is_ascii_digit()));
    let has_unit = tokens.iter().any(|token| {
        let word = lower_word(token);
        UNITS.iter().any(|unit| unit == &word)
    });
    if has_digit && !has_unit {
        mask |= GAP_UNEXPLAINED_NUMBER;
    }

    let tail = line.trim_end();
    let ends_open = tail.ends_with(',')
        || tail.ends_with(';')
        || tail.ends_with('-')
        || tail.ends_with('—')
        || tail.ends_with('|')
        || tail.ends_with(" and")
        || tail.ends_with(" or");
    if ends_open {
        mask |= GAP_TRUNCATED;
    }

    let mut run = 0;
    let mut best = 0;
    for token in &tokens {
        let bare = token.trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '_');
        let capitalised = bare
            .chars()
            .next()
            .map(|c| c.is_ascii_uppercase())
            .unwrap_or(false);
        if capitalised {
            run += 1;
            best = best.max(run);
        } else {
            run = 0;
        }
    }
    if best >= 6 {
        mask |= GAP_NOUN_CHAIN;
    }

    (mask, words)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn analyse(text: &str) -> Vec<(u32, u32, u32)> {
        // The ABI writes into the static input; the test must do the same.
        unsafe { INPUT[..text.len()].copy_from_slice(text.as_bytes()) };
        let lines = crudity_analyse(text.len() as u32);
        (0..lines)
            .map(|i| (crudity_mask(i), crudity_grade(i), crudity_words(i)))
            .collect()
    }

    /// A line that names its subject and its effect is classified as whole.
    #[test]
    fn a_full_sentence_that_names_its_subject_and_its_effect_is_classified_whole() {
        let rows = analyse("The dock reserves its strip before it paints, so no frame is drawn over a work area it does not own.");
        assert_eq!(rows[0].1, 0, "expected whole, mask {}", rows[0].0);
    }

    /// A bold lead with no rule under it is refused as a lossy line.
    #[test]
    fn a_bold_lead_with_no_rule_under_it_is_refused_as_a_lossy_line() {
        let rows = analyse("- **A live compile can actually be stopped.**");
        assert_eq!(rows[0].0 & GAP_BOLD_LEAD_ONLY, GAP_BOLD_LEAD_ONLY, "mask {}", rows[0].0);
        assert_eq!(rows[0].1, 1, "mask {}", rows[0].0);
    }

    /// A pointer where the reasoning belonged is refused by its own name.
    #[test]
    fn a_pointer_where_the_reasoning_belonged_is_refused_by_name() {
        let rows = analyse("- see docs/history for the rest.");
        assert_eq!(rows[0].0 & GAP_POINTER_INSTEAD, GAP_POINTER_INSTEAD);
    }

    /// Semicolons, counters and bare numbers together are a shorthand line.
    #[test]
    fn a_semicolon_counter_dump_with_bare_numbers_is_classified_shorthand() {
        let rows = analyse("- **Relevant.** See above; 4 counters; 2 flags");
        assert_eq!(rows[0].1, 3);
        let mask = rows[0].0;
        assert_eq!(mask & GAP_SEMICOLON_DUMP, GAP_SEMICOLON_DUMP);
        assert_eq!(mask & GAP_POINTER_INSTEAD, GAP_POINTER_INSTEAD);
        assert_eq!(mask & GAP_UNEXPLAINED_NUMBER, GAP_UNEXPLAINED_NUMBER);
    }

    /// Blank and whitespace only lines are not classified at all.
    #[test]
    fn blank_and_whitespace_only_lines_are_not_classified_at_all() {
        let rows = analyse("\n\n   \nA dock that hides the tile bar is a dock the owner keeps.\n");
        assert_eq!(rows.len(), 1);
    }
}
