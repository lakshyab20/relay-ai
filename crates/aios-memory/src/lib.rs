use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntity {
    pub id: String,
    pub content: String,
    pub embedding: Vec<f32>,
    pub timestamp: i64,
}

pub struct SemanticStore {
    entities: RwLock<HashMap<String, MemoryEntity>>,
}

impl SemanticStore {
    pub fn new() -> Self {
        Self {
            entities: RwLock::new(HashMap::new()),
        }
    }

    pub fn insert(&self, entity: MemoryEntity) {
        let mut store = self.entities.write().unwrap();
        store.insert(entity.id.clone(), entity);
    }

    pub fn search(&self, query_vec: &[f32], top_k: usize) -> Vec<(String, f32)> {
        let store = self.entities.read().unwrap();
        let mut scored: Vec<(String, f32)> = store
            .values()
            .map(|e| {
                let sim = cosine_similarity(query_vec, &e.embedding);
                (e.content.clone(), sim)
            })
            .collect();

        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(top_k);
        scored
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm_a == 0.0 || norm_b == 0.0 {
        0.0
    } else {
        dot / (norm_a * norm_b)
    }
}
