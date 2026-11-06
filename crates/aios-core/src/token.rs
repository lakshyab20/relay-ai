use chrono::{DateTime, Duration, Utc};
use ring::hmac;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

#[derive(Error, Debug)]
pub enum TokenError {
    #[error("Token has expired")]
    Expired,
    #[error("Cryptographic signature mismatch")]
    InvalidSignature,
    #[error("Unauthorized capability requested: {0}")]
    Unauthorized(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ActionScope {
    MemoryRead { namespace: String },
    MemoryWrite { namespace: String },
    ToolExecute { tool_name: String },
    NetworkEgress { host: String, port: u16 },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityToken {
    pub id: Uuid,
    pub agent_id: String,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub scopes: Vec<ActionScope>,
    pub max_tokens: usize,
    pub signature: Vec<u8>,
}

pub struct CapabilityEngine {
    key: hmac::Key,
}

impl CapabilityEngine {
    pub fn new(secret_bytes: &[u8]) -> Self {
        let key = hmac::Key::new(hmac::HMAC_SHA256, secret_bytes);
        Self { key }
    }

    pub fn issue_token(
        &self,
        agent_id: &str,
        scopes: Vec<ActionScope>,
        ttl_seconds: i64,
        max_tokens: usize,
    ) -> CapabilityToken {
        let id = Uuid::new_v4();
        let issued_at = Utc::now();
        let expires_at = issued_at + Duration::seconds(ttl_seconds);

        let payload = format!(
            "{}:{}:{}:{}:{}",
            id,
            agent_id,
            issued_at.timestamp(),
            expires_at.timestamp(),
            max_tokens
        );
        let tag = hmac::sign(&self.key, payload.as_bytes());

        CapabilityToken {
            id,
            agent_id: agent_id.to_string(),
            issued_at,
            expires_at,
            scopes,
            max_tokens,
            signature: tag.as_ref().to_vec(),
        }
    }

    pub fn verify_token(
        &self,
        token: &CapabilityToken,
        requested_scope: &ActionScope,
    ) -> Result<(), TokenError> {
        if Utc::now() > token.expires_at {
            return Err(TokenError::Expired);
        }

        let payload = format!(
            "{}:{}:{}:{}:{}",
            token.id,
            token.agent_id,
            token.issued_at.timestamp(),
            token.expires_at.timestamp(),
            token.max_tokens
        );
        if hmac::verify(&self.key, payload.as_bytes(), &token.signature).is_err() {
            return Err(TokenError::InvalidSignature);
        }

        let has_permission = token
            .scopes
            .iter()
            .any(|scope| match (scope, requested_scope) {
                (
                    ActionScope::MemoryRead { namespace: s1 },
                    ActionScope::MemoryRead { namespace: s2 },
                ) => s1 == s2 || s1 == "*",
                (
                    ActionScope::MemoryWrite { namespace: s1 },
                    ActionScope::MemoryWrite { namespace: s2 },
                ) => s1 == s2 || s1 == "*",
                (
                    ActionScope::ToolExecute { tool_name: t1 },
                    ActionScope::ToolExecute { tool_name: t2 },
                ) => t1 == t2 || t1 == "*",
                (
                    ActionScope::NetworkEgress { host: h1, port: p1 },
                    ActionScope::NetworkEgress { host: h2, port: p2 },
                ) => (h1 == h2 || h1 == "*") && (p1 == p2 || *p1 == 0),
                _ => false,
            });

        if !has_permission {
            return Err(TokenError::Unauthorized(format!("{:?}", requested_scope)));
        }

        Ok(())
    }
}
