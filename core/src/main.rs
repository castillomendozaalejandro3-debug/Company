use tonic::{transport::Server, Request, Response, Status};
use tokio::net::TcpListener;
use sysinfo::{System, SystemExt, DiskExt};
use log::{info, warn};
use std::env;

pub mod helios {
    tonic::include_proto!("helios");
}

use helios::{
    helios_core_server::{HeliosCore, HeliosCoreServer},
    Empty, PingRequest, PingResponse, SystemMetrics, ValidateActionRequest, 
    ValidateActionResponse, DiskInfo,
};

#[derive(Default)]
pub struct HeliosCoreService {
    system: System,
}

#[tonic::async_trait]
impl HeliosCore for HeliosCoreService {
    async fn ping(
        &self,
        request: Request<PingRequest>,
    ) -> Result<Response<PingResponse>, Status> {
        let msg = request.into_inner().message;
        info!("Ping recibido: {}", msg);
        
        Ok(Response::new(PingResponse {
            message: format!("Pong! Recibido: {}", msg),
            timestamp: chrono::Utc::now().timestamp(),
        }))
    }

    async fn get_system_metrics(
        &self,
        _request: Request<Empty>,
    ) -> Result<Response<SystemMetrics>, Status> {
        let mut system = System::new_all();
        system.refresh_all();

        let cpu_usage = system.global_cpu_info().cpu_usage() as f32;
        let total_memory = system.total_memory();
        let used_memory = system.used_memory();
        let memory_usage_percent = (used_memory as f32 / total_memory as f32) * 100.0;

        let disks: Vec<DiskInfo> = system
            .disks()
            .iter()
            .map(|disk| DiskInfo {
                name: disk.mount_point().to_string_lossy().into_owned(),
                total_space: disk.total_space(),
                used_space: disk.total_space() - disk.available_space(),
                usage_percent: ((disk.total_space() - disk.available_space()) as f32 
                    / disk.total_space() as f32) * 100.0,
            })
            .collect();

        info!("Métricas del sistema obtenidas: CPU {}%, RAM {}%", 
              cpu_usage, memory_usage_percent);

        Ok(Response::new(SystemMetrics {
            cpu_usage,
            total_memory,
            used_memory,
            memory_usage_percent,
            disks,
        }))
    }

    async fn validate_action(
        &self,
        request: Request<ValidateActionRequest>,
    ) -> Result<Response<ValidateActionResponse>, Status> {
        let inner = request.into_inner();
        let action = inner.action.to_lowercase();
        let target = inner.target.to_lowercase();

        // Lista de acciones peligrosas
        let dangerous_actions = ["delete", "format", "rm", "del", "shutdown", "restart"];
        let dangerous_targets = ["/etc/shadow", "/etc/passwd", "c:\\windows\\system32"];

        let is_dangerous_action = dangerous_actions.iter().any(|a| action.contains(a));
        let is_dangerous_target = dangerous_targets.iter().any(|t| target.contains(t));

        let (is_safe, reason, risk_score) = if is_dangerous_action || is_dangerous_target {
            warn!("Acción peligrosa detectada: {} en {}", action, target);
            (false, "Acción bloqueada por políticas de seguridad".to_string(), 0.9)
        } else {
            info!("Acción validada como segura: {} en {}", action, target);
            (true, "Acción permitida".to_string(), 0.1)
        };

        Ok(Response::new(ValidateActionResponse {
            is_safe,
            reason,
            risk_score,
        }))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();
    
    let addr = env::var("HELIOS_CORE_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:50051".to_string());
    
    let listener = TcpListener::bind(addr.clone()).await?;
    info!("Servidor Helios Core escuchando en {}", addr);

    let service = HeliosCoreService::default();

    Server::builder()
        .add_service(HeliosCoreServer::new(service))
        .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(listener))
        .await?;

    Ok(())
}
