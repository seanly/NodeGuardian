#!/usr/bin/env bash

# NodeGuardian Shell Version Deployment Script
# 部署和清理NodeGuardian shell-operator

set -euo pipefail

# 配置
NAMESPACE="nodeguardian-system"
IMAGE_NAME="nodeguardian-shell"
IMAGE_TAG="latest"
REGISTRY="${REGISTRY:-}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat <<EOF
NodeGuardian Shell Version Deployment Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build       Build the Docker image
    deploy      Deploy NodeGuardian to Kubernetes
    undeploy    Remove NodeGuardian from Kubernetes
    clean       Clean up all resources
    status      Show deployment status
    logs        Show logs
    help        Show this help message

Options:
    --namespace NAME     Kubernetes namespace (default: $NAMESPACE)
    --image-name NAME    Docker image name (default: $IMAGE_NAME)
    --image-tag TAG      Docker image tag (default: $IMAGE_TAG)
    --registry URL       Docker registry URL
    --help               Show this help message

Examples:
    $0 build
    $0 deploy
    $0 deploy --namespace my-namespace
    $0 build --registry my-registry.com
    $0 clean
EOF
}

# 检查依赖
check_dependencies() {
    local deps=("kubectl" "docker")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            log_error "Required command '$dep' not found"
            exit 1
        fi
    done
}

# 构建Docker镜像
build_image() {
    log_info "Building NodeGuardian Docker image..."
    
    local full_image_name="$IMAGE_NAME:$IMAGE_TAG"
    if [[ -n "$REGISTRY" ]]; then
        full_image_name="$REGISTRY/$full_image_name"
    fi
    
    log_info "Building image: $full_image_name"
    
    docker build -t "$full_image_name" -f deploy/Dockerfile . || {
        log_error "Failed to build Docker image"
        exit 1
    }
    
    log_info "Docker image built successfully: $full_image_name"
}

# 部署到Kubernetes
deploy_to_k8s() {
    log_info "Deploying NodeGuardian to Kubernetes..."
    
    # 检查kubectl连接
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # 创建命名空间
    log_info "Creating namespace: $NAMESPACE"
    kubectl apply -f deploy/namespace.yaml
    
    # 应用CRDs
    log_info "Applying Custom Resource Definitions..."
    kubectl apply -f crd/nodeguardianrule-crd.yaml
    kubectl apply -f crd/alerttemplate-crd.yaml
    
    # 应用RBAC
    log_info "Applying RBAC configuration..."
    kubectl apply -f deploy/rbac.yaml
    
    # 构建并推送镜像（如果需要）
    if [[ -n "$REGISTRY" ]]; then
        build_image
        log_info "Pushing image to registry..."
        docker push "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    fi
    
    # 应用部署
    log_info "Applying deployment..."
    envsubst < deploy/deployment.yaml | kubectl apply -f -
    
    # 等待部署完成
    log_info "Waiting for deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/nodeguardian-controller -n "$NAMESPACE"
    
    log_info "NodeGuardian deployed successfully!"
    show_status
}

# 从Kubernetes删除
undeploy_from_k8s() {
    log_info "Removing NodeGuardian from Kubernetes..."
    
    # 删除部署
    log_info "Deleting deployment..."
    kubectl delete -f deploy/deployment.yaml --ignore-not-found=true
    
    # 删除RBAC
    log_info "Deleting RBAC configuration..."
    kubectl delete -f deploy/rbac.yaml --ignore-not-found=true
    
    # 删除CRDs
    log_info "Deleting Custom Resource Definitions..."
    kubectl delete -f crd/alerttemplate-crd.yaml --ignore-not-found=true
    kubectl delete -f crd/nodeguardianrule-crd.yaml --ignore-not-found=true
    
    # 删除命名空间
    log_info "Deleting namespace: $NAMESPACE"
    kubectl delete -f deploy/namespace.yaml --ignore-not-found=true
    
    log_info "NodeGuardian removed from Kubernetes!"
}

# 清理所有资源
clean_all() {
    log_info "Cleaning up all NodeGuardian resources..."
    
    # 删除所有NodeGuardianRule和AlertTemplate
    log_info "Deleting all NodeGuardianRule objects..."
    kubectl delete nodeguardianrules --all --all-namespaces --ignore-not-found=true
    
    log_info "Deleting all AlertTemplate objects..."
    kubectl delete alerttemplates --all --all-namespaces --ignore-not-found=true
    
    # 删除部署
    undeploy_from_k8s
    
    # 清理本地镜像
    if [[ -n "$REGISTRY" ]]; then
        log_info "Removing local Docker image..."
        docker rmi "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG" 2>/dev/null || true
    else
        log_info "Removing local Docker image..."
        docker rmi "$IMAGE_NAME:$IMAGE_TAG" 2>/dev/null || true
    fi
    
    log_info "Cleanup completed!"
}

# 显示部署状态
show_status() {
    log_info "NodeGuardian Deployment Status:"
    echo
    
    # 命名空间状态
    log_info "Namespace:"
    kubectl get namespace "$NAMESPACE" 2>/dev/null || log_warn "Namespace not found"
    echo
    
    # 部署状态
    log_info "Deployment:"
    kubectl get deployment nodeguardian-controller -n "$NAMESPACE" 2>/dev/null || log_warn "Deployment not found"
    echo
    
    # Pod状态
    log_info "Pods:"
    kubectl get pods -n "$NAMESPACE" -l app=nodeguardian-controller 2>/dev/null || log_warn "Pods not found"
    echo
    
    # 服务状态
    log_info "Services:"
    kubectl get services -n "$NAMESPACE" 2>/dev/null || log_warn "Services not found"
    echo
    
    # CRD状态
    log_info "Custom Resource Definitions:"
    kubectl get crd | grep nodeguardian || log_warn "CRDs not found"
    echo
    
    # 资源对象状态
    log_info "NodeGuardianRule objects:"
    kubectl get nodeguardianrules --all-namespaces 2>/dev/null || log_warn "No NodeGuardianRule objects found"
    echo
    
    log_info "AlertTemplate objects:"
    kubectl get alerttemplates --all-namespaces 2>/dev/null || log_warn "No AlertTemplate objects found"
    echo
}

# 显示日志
show_logs() {
    log_info "Showing NodeGuardian logs..."
    
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l app=nodeguardian-controller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod_name" ]]; then
        log_error "No NodeGuardian pods found"
        exit 1
    fi
    
    kubectl logs -f "$pod_name" -n "$NAMESPACE"
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            build|deploy|undeploy|clean|status|logs|help)
                COMMAND="$1"
                shift
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --image-name)
                IMAGE_NAME="$2"
                shift 2
                ;;
            --image-tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            --registry)
                REGISTRY="$2"
                shift 2
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# 主函数
main() {
    # 设置默认命令
    COMMAND="${1:-help}"
    
    # 解析参数
    parse_args "$@"
    
    # 检查依赖
    check_dependencies
    
    # 导出环境变量供envsubst使用
    export NAMESPACE IMAGE_NAME IMAGE_TAG REGISTRY
    
    # 执行命令
    case "$COMMAND" in
        build)
            build_image
            ;;
        deploy)
            deploy_to_k8s
            ;;
        undeploy)
            undeploy_from_k8s
            ;;
        clean)
            clean_all
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        help)
            show_help
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"