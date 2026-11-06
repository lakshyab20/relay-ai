use std::fs;
use std::path::{Path, PathBuf};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum SandboxError {
    #[error("Unknown tool requested: {0}")]
    UnknownTool(String),
    #[error("Path escape attempted outside sandbox: {0}")]
    PathEscape(String),
    #[error("Execution error: {0}")]
    Execution(String),
}

pub struct SandboxedActuator {
    base_dir: PathBuf,
}

impl SandboxedActuator {
    pub fn new<P: AsRef<Path>>(base_dir: P) -> Self {
        Self {
            base_dir: base_dir.as_ref().to_path_buf(),
        }
    }

    fn sanitize_path(&self, target: &str) -> Result<PathBuf, SandboxError> {
        let path = if Path::new(target).is_absolute() {
            PathBuf::from(target)
        } else {
            self.base_dir.join(target)
        };

        let canon = path.canonicalize().unwrap_or_else(|_| path.clone());

        if !canon.starts_with(&self.base_dir) && !canon.starts_with("/tmp") {
            return Err(SandboxError::PathEscape(target.to_string()));
        }
        Ok(canon)
    }

    pub fn execute(&self, tool: &str, params: &str) -> Result<String, SandboxError> {
        match tool {
            "eval_math" => self.eval_math(params),
            "fs_read" => self.fs_read(params),
            "fs_write" => self.fs_write(params),
            "sys_info" => Ok(format!(
                "OS: macOS Darwin | Arch: {} | Cores: {}",
                std::env::consts::ARCH,
                num_cpus()
            )),
            _ => Err(SandboxError::UnknownTool(tool.to_string())),
        }
    }

    fn eval_math(&self, expr: &str) -> Result<String, SandboxError> {
        let clean = expr.trim_start_matches("calculate").trim();
        let (left, right, op) = if let Some((l, r)) = clean.split_once('*') {
            (l, r, '*')
        } else if let Some((l, r)) = clean.split_once('+') {
            (l, r, '+')
        } else if let Some((l, r)) = clean.split_once('-') {
            (l, r, '-')
        } else if let Some((l, r)) = clean.split_once('/') {
            (l, r, '/')
        } else {
            return Ok(clean.to_string());
        };

        let l_num: f64 = left
            .trim()
            .parse()
            .map_err(|e| SandboxError::Execution(format!("{:?}", e)))?;
        let r_num: f64 = right
            .trim()
            .parse()
            .map_err(|e| SandboxError::Execution(format!("{:?}", e)))?;

        let res = match op {
            '*' => l_num * r_num,
            '+' => l_num + r_num,
            '-' => l_num - r_num,
            '/' => {
                if r_num == 0.0 {
                    return Err(SandboxError::Execution("Division by zero".into()));
                }
                l_num / r_num
            }
            _ => unreachable!(),
        };

        Ok(format!("{} = {}", clean, res))
    }

    fn fs_read(&self, target: &str) -> Result<String, SandboxError> {
        let path = self.sanitize_path(target)?;
        let content = fs::read_to_string(&path)
            .map_err(|e| SandboxError::Execution(format!("Read failed: {:?}", e)))?;
        Ok(content)
    }

    fn fs_write(&self, params_json: &str) -> Result<String, SandboxError> {
        // Format: "path:::content"
        if let Some((path_str, content)) = params_json.split_once(":::") {
            let path = self.sanitize_path(path_str.trim())?;
            if let Some(parent) = path.parent() {
                let _ = fs::create_dir_all(parent);
            }
            fs::write(&path, content)
                .map_err(|e| SandboxError::Execution(format!("Write failed: {:?}", e)))?;
            Ok(format!(
                "Wrote {} bytes to {}",
                content.len(),
                path.display()
            ))
        } else {
            Err(SandboxError::Execution(
                "Invalid fs_write payload, expected 'path:::content'".into(),
            ))
        }
    }
}

fn num_cpus() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
}
