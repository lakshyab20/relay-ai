use regex::Regex;
use std::sync::OnceLock;

static API_KEY_REGEX: OnceLock<Regex> = OnceLock::new();
static GITHUB_KEY_REGEX: OnceLock<Regex> = OnceLock::new();
static PROMPT_INJECTION_REGEX: OnceLock<Regex> = OnceLock::new();

pub struct DLPScanner;

impl DLPScanner {
    pub fn sanitize(text: &str) -> (String, bool) {
        let api_re = API_KEY_REGEX.get_or_init(|| Regex::new(r"sk-[a-zA-Z0-9]{20,}").unwrap());
        let ghp_re = GITHUB_KEY_REGEX.get_or_init(|| Regex::new(r"ghp_[a-zA-Z0-9]{20,}").unwrap());

        let mut sanitized = text.to_string();
        let mut leaked = false;

        if api_re.is_match(&sanitized) {
            leaked = true;
            sanitized = api_re
                .replace_all(&sanitized, "[REDACTED_API_KEY]")
                .to_string();
        }
        if ghp_re.is_match(&sanitized) {
            leaked = true;
            sanitized = ghp_re
                .replace_all(&sanitized, "[REDACTED_GITHUB_TOKEN]")
                .to_string();
        }

        (sanitized, leaked)
    }
}

pub struct PromptInjectionGuard;

impl PromptInjectionGuard {
    pub fn inspect(prompt: &str) -> Result<(), String> {
        let inj_re = PROMPT_INJECTION_REGEX.get_or_init(|| {
            Regex::new(r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|system\s+override|exfiltrate\s+to)").unwrap()
        });

        if let Some(mat) = inj_re.find(prompt) {
            Err(format!(
                "PromptInjectionDetected: Matched adversarial pattern '{}'",
                mat.as_str()
            ))
        } else {
            Ok(())
        }
    }
}
