#!/bin/bash

# NodeGuardian Python版本部署脚本
# 用于部署基于Python的NodeGuardian到Kubernetes集群

set -euo pipefail

# 配置变量
NAMESPACE="nodeguardian-system"
IMAGE_NAME="nodeguardian-python"
IMAGE_TAG="latest"
REGISTRY="${REGISTRY:-}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case "$level" in
        "INFO")
            echo -e "${GREEN}[$timestamp] [INFO]${NC} $message"
            ;;
        "WARN")
            echo -e "${YELLOW}[$timestamp] [WARN]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[$timestamp] [ERROR]${NC} $message"
            ;;
        "DEBUG")
            echo -e "${BLUE}[$timestamp] [DEBUG]${NC} $message"
            ;;
    esac
}

# 检查命令是否存在
check_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "ERROR" "Command '$cmd' not found. Please install it first."
        exit 1
    fi
}

# 检查必要的命令
check_requirements() {
    log "INFO" "Checking requirements..."
    
    local commands=("kubectl" "docker")
    for cmd in "${commands[@]}"; do
        check_command "$cmd"
    done
    
    # 检查kubectl连接
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log "ERROR" "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
        exit 1
    fi
    
    log "INFO" "Requirements check passed"
}

# 构建Docker镜像
build_image() {
    log "INFO" "Building NodeGuardian Python Docker image..."
    
    local full_image_name="$IMAGE_NAME:$IMAGE_TAG"
    if [[ -n "$REGISTRY" ]]; then
        full_image_name="$REGISTRY/$full_image_name"
    fi
    
    # 构建镜像
    docker build -t "$full_image_name" -f deploy/Dockerfile .
    
    log "INFO" "Docker image built: $full_image_name"
    
    # 推送到镜像仓库（如果指定了registry）
    if [[ -n "$REGISTRY" ]]; then
        log "INFO" "Pushing image to registry..."
        docker push "$full_image_name"
        log "INFO" "Image pushed to registry"
    fi
    
    echo "$full_image_name"
}

# 部署CRD
deploy_crds() {
    log "INFO" "Deploying CRDs..."
    
    kubectl apply -f ../crd/nodeguardianrule-crd.yaml
    kubectl apply -f ../crd/alerttemplate-crd.yaml
    
    # 等待CRD就绪
    log "INFO" "Waiting for CRDs to be ready..."
    kubectl wait --for=condition=Established --timeout=60s crd/nodeguardianrules.nodeguardian.k8s.io
    kubectl wait --for=condition=Established --timeout=60s crd/alerttemplates.nodeguardian.k8s.io
    
    log "INFO" "CRDs deployed successfully"
}

# 部署命名空间
deploy_namespace() {
    log "INFO" "Deploying namespace..."
    
    kubectl apply -f ../deploy/namespace.yaml
    
    log "INFO" "Namespace deployed successfully"
}

# 部署RBAC
deploy_rbac() {
    log "INFO" "Deploying RBAC..."
    
    kubectl apply -f ../deploy/rbac.yaml
    
    log "INFO" "RBAC deployed successfully"
}

# 部署应用
deploy_application() {
    local image_name="$1"
    
    log "INFO" "Deploying NodeGuardian Python application..."
    
    # 更新镜像名称
    sed "s|image: nodeguardian-python:latest|image: $image_name|g" deploy/deployment.yaml | kubectl apply -f -
    
    # 等待部署就绪
    log "INFO" "Waiting for deployment to be ready..."
    kubectl wait --for=condition=Available --timeout=300s deployment/nodeguardian-python -n "$NAMESPACE"
    
    log "INFO" "Application deployed successfully"
}

# 部署示例
deploy_examples() {
    log "INFO" "Deploying examples..."
    
    # 部署告警模板
    kubectl apply -f ../examples/alert-templates.yaml
    
    # 部署示例规则
    kubectl apply -f ../examples/high-load-isolation.yaml
    kubectl apply -f ../examples/disk-space-alert.yaml
    kubectl apply -f ../examples/emergency-eviction.yaml
    
    log "INFO" "Examples deployed successfully"
}

# 验证部署
verify_deployment() {
    log "INFO" "Verifying deployment..."
    
    # 检查Pod状态
    local pod_status=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/implementation=python -o jsonpath='{.items[0].status.phase}')
    if [[ "$pod_status" != "Running" ]]; then
        log "ERROR" "NodeGuardian Python pod is not running. Status: $pod_status"
        return 1
    fi
    
    # 检查服务状态
    if ! kubectl get service nodeguardian-python -n "$NAMESPACE" >/dev/null 2>&1; then
        log "ERROR" "NodeGuardian Python service not found"
        return 1
    fi
    
    # 检查CRD状态
    if ! kubectl get crd nodeguardianrules.nodeguardian.k8s.io >/dev/null 2>&1; then
        log "ERROR" "NodeGuardianRule CRD not found"
        return 1
    fi
    
    if ! kubectl get crd alerttemplates.nodeguardian.k8s.io >/dev/null 2>&1; then
        log "ERROR" "AlertTemplate CRD not found"
        return 1
    fi
    
    log "INFO" "Deployment verification passed"
}

# 显示状态
show_status() {
    log "INFO" "NodeGuardian Python deployment status:"
    
    echo ""
    echo "=== Namespace ==="
    kubectl get namespace "$NAMESPACE"
    
    echo ""
    echo "=== Pods ==="
    kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/implementation=python
    
    echo ""
    echo "=== Services ==="
    kubectl get services -n "$NAMESPACE"
    
    echo ""
    echo "=== CRDs ==="
    kubectl get crd | grep nodeguardian
    
    echo ""
    echo "=== NodeGuardianRules ==="
    kubectl get nodeguardianrules
    
    echo ""
    echo "=== AlertTemplates ==="
    kubectl get alerttemplates
}

# 清理部署
cleanup() {
    log "INFO" "Cleaning up NodeGuardian Python deployment..."
    
    # 删除示例
    kubectl delete -f ../examples/ --ignore-not-found=true
    
    # 删除应用
    kubectl delete -f deploy/deployment.yaml --ignore-not-found=true
    
    # 删除RBAC
    kubectl delete -f ../deploy/rbac.yaml --ignore-not-found=true
    
    # 删除命名空间
    kubectl delete -f ../deploy/namespace.yaml --ignore-not-found=true
    
    # 删除CRD
    kubectl delete -f ../crd/ --ignore-not-found=true
    
    log "INFO" "Cleanup completed"
}

# 显示帮助
show_help() {
    cat <<EOF
NodeGuardian Python版本部署脚本

用法: $0 [选项]

选项:
    -h, --help              显示此帮助信息
    -b, --build             构建Docker镜像
    -d, --deploy            部署NodeGuardian
    -e, --examples          部署示例
    -v, --verify            验证部署
    -s, --status            显示状态
    -c, --cleanup           清理部署
    -f, --full              完整部署（构建+部署+示例+验证）
    --registry REGISTRY     指定镜像仓库
    --tag TAG               指定镜像标签
    --namespace NAMESPACE   指定命名空间

示例:
    $0 --full                    # 完整部署
    $0 --build --deploy          # 构建并部署
    $0 --status                  # 查看状态
    $0 --cleanup                 # 清理部署

环境变量:
    REGISTRY                   镜像仓库地址
    NAMESPACE                  部署命名空间（默认: nodeguardian-system）

EOF
}

# 主函数
main() {
    local build=false
    local deploy=false
    local examples=false
    local verify=false
    local status=false
    local cleanup_flag=false
    local full=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -b|--build)
                build=true
                shift
                ;;
            -d|--deploy)
                deploy=true
                shift
                ;;
            -e|--examples)
                examples=true
                shift
                ;;
            -v|--verify)
                verify=true
                shift
                ;;
            -s|--status)
                status=true
                shift
                ;;
            -c|--cleanup)
                cleanup_flag=true
                shift
                ;;
            -f|--full)
                full=true
                shift
                ;;
            --registry)
                REGISTRY="$2"
                shift 2
                ;;
            --tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            *)
                log "ERROR" "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 如果没有指定任何选项，显示帮助
    if [[ "$build" == false && "$deploy" == false && "$examples" == false && "$verify" == false && "$status" == false && "$cleanup_flag" == false && "$full" == false ]]; then
        show_help
        exit 0
    fi
    
    # 检查要求
    check_requirements
    
    # 执行操作
    if [[ "$cleanup_flag" == true ]]; then
        cleanup
        exit 0
    fi
    
    if [[ "$status" == true ]]; then
        show_status
        exit 0
    fi
    
    local image_name=""
    
    if [[ "$full" == true ]]; then
        log "INFO" "Starting full deployment..."
        
        # 构建镜像
        image_name=$(build_image)
        
        # 部署CRD
        deploy_crds
        
        # 部署命名空间
        deploy_namespace
        
        # 部署RBAC
        deploy_rbac
        
        # 部署应用
        deploy_application "$image_name"
        
        # 部署示例
        deploy_examples
        
        # 验证部署
        verify_deployment
        
        # 显示状态
        show_status
        
        log "INFO" "Full deployment completed successfully!"
        
    else
        if [[ "$build" == true ]]; then
            image_name=$(build_image)
        fi
        
        if [[ "$deploy" == true ]]; then
            deploy_crds
            deploy_namespace
            deploy_rbac
            deploy_application "${image_name:-nodeguardian-python:latest}"
        fi
        
        if [[ "$examples" == true ]]; then
            deploy_examples
        fi
        
        if [[ "$verify" == true ]]; then
            verify_deployment
        fi
    fi
}

# 执行主函数
main "$@"
