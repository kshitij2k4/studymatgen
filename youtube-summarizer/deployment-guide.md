# Deployment Guide for YouTube Summarizer

## Overview
This guide covers various deployment options for the YouTube Summarizer that uses local Ollama and Whisper models.

## 1. Docker Deployment (Recommended)

### Prerequisites
- Docker with GPU support (nvidia-docker2)
- NVIDIA GPU with CUDA support
- At least 8GB GPU memory

### Quick Start
```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build manually
docker build -t youtube-summarizer .
docker run --gpus all -p 5000:5000 -v $(pwd)/outputs:/app/outputs youtube-summarizer
```

### Benefits
- ✅ Consistent environment across deployments
- ✅ Easy to scale and manage
- ✅ GPU support included
- ✅ All dependencies bundled

## 2. Cloud Platform Deployments

### A. AWS EC2 with GPU
**Best for: Production deployments with high performance needs**

#### Instance Requirements:
- **Instance Type**: g4dn.xlarge or p3.2xlarge (GPU instances)
- **Storage**: 50GB+ EBS volume
- **Memory**: 16GB+ RAM
- **OS**: Ubuntu 22.04 LTS

#### Setup Steps:
```bash
# 1. Launch GPU-enabled EC2 instance
# 2. Install NVIDIA drivers and Docker
sudo apt update
sudo apt install -y nvidia-driver-470 docker.io
sudo systemctl start docker

# 3. Install nvidia-docker2
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-docker2
sudo systemctl restart docker

# 4. Deploy your application
git clone <your-repo>
cd youtube-summarizer
docker-compose up -d
```

#### Cost Estimate:
- g4dn.xlarge: ~$0.526/hour (~$380/month)
- p3.2xlarge: ~$3.06/hour (~$2,200/month)

### B. Google Cloud Platform (GCP)
**Best for: Flexible scaling and preemptible instances**

#### Setup:
```bash
# 1. Create VM with GPU
gcloud compute instances create youtube-summarizer \
    --zone=us-central1-a \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --image-family=ubuntu-2004-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=50GB \
    --maintenance-policy=TERMINATE \
    --restart-on-failure

# 2. SSH and setup
gcloud compute ssh youtube-summarizer --zone=us-central1-a

# 3. Install dependencies (same as AWS steps above)
```

#### Cost Estimate:
- n1-standard-4 + T4 GPU: ~$0.35/hour (~$250/month)
- Preemptible: ~$0.11/hour (~$80/month)

### C. Azure VM
**Best for: Enterprise environments**

#### Setup:
```bash
# Create resource group
az group create --name youtube-summarizer-rg --location eastus

# Create VM with GPU
az vm create \
    --resource-group youtube-summarizer-rg \
    --name youtube-summarizer-vm \
    --image UbuntuLTS \
    --size Standard_NC6s_v3 \
    --admin-username azureuser \
    --generate-ssh-keys

# Install NVIDIA drivers and Docker (same as above)
```

## 3. VPS Deployment (Budget Option)

### Providers with GPU Support:
- **Vast.ai**: $0.10-0.50/hour for GPU instances
- **RunPod**: $0.15-0.80/hour for GPU instances
- **Lambda Labs**: $0.50-2.00/hour for GPU instances

### Setup:
```bash
# 1. Rent GPU instance
# 2. Clone repository
git clone <your-repo>
cd youtube-summarizer

# 3. Install dependencies
sudo apt update
sudo apt install -y python3-pip ffmpeg
pip3 install -r requirements.txt

# 4. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
ollama pull llama3.2:3b

# 5. Run application
python3 app.py
```

## 4. Self-Hosted Options

### A. Home Server/Workstation
**Requirements:**
- NVIDIA GPU (GTX 1060 6GB minimum, RTX 3060+ recommended)
- 16GB+ RAM
- Ubuntu/Windows with WSL2
- Static IP or Dynamic DNS

### B. Raspberry Pi Cluster (CPU-only)
**For lightweight deployments without GPU:**
```bash
# Use smaller models
# Modify app.py to use CPU-only Whisper models
# Use lighter Ollama models like llama3.2:1b
```

## 5. Serverless Alternatives

### A. Modal.com
**Best for: Pay-per-use with GPU support**

```python
# modal_app.py
import modal

stub = modal.Stub("youtube-summarizer")

@stub.function(
    image=modal.Image.debian_slim().pip_install_from_requirements("requirements.txt"),
    gpu="T4",
    timeout=3600
)
def process_video(url):
    # Your processing logic here
    pass
```

### B. Replicate.com
**Best for: API-based deployment**

Create a cog.yaml and deploy as a Replicate model.

## 6. Production Considerations

### Security
```bash
# Add nginx reverse proxy
# Enable HTTPS with Let's Encrypt
# Set up firewall rules
# Use environment variables for secrets
```

### Monitoring
```bash
# Add health checks
# Set up logging
# Monitor GPU usage
# Set up alerts
```

### Scaling
```bash
# Use load balancer
# Implement job queuing (Redis/Celery)
# Add horizontal scaling
```

## 7. Cost Comparison

| Option | Monthly Cost | GPU | Setup Difficulty | Best For |
|--------|-------------|-----|------------------|----------|
| Home Server | $0 (electricity) | Your GPU | Medium | Development/Personal |
| Vast.ai | $50-150 | Various | Easy | Budget Production |
| GCP Preemptible | $80-120 | T4/V100 | Medium | Cost-effective Production |
| AWS EC2 | $380-2200 | Various | Medium | Enterprise Production |
| Modal.com | Pay-per-use | T4/A100 | Easy | Sporadic Usage |

## 8. Recommended Deployment Strategy

### For Development:
- Local development with Docker
- Test with smaller models first

### For Production:
1. **Small Scale**: VPS with GPU (Vast.ai, RunPod)
2. **Medium Scale**: GCP with preemptible instances
3. **Large Scale**: AWS/Azure with auto-scaling
4. **Enterprise**: On-premises with Kubernetes

## 9. Quick Deploy Commands

### Docker (Local):
```bash
docker-compose up --build
```

### AWS (with Terraform):
```bash
terraform init
terraform plan
terraform apply
```

### GCP (with gcloud):
```bash
gcloud compute instances create-with-container youtube-summarizer \
    --container-image=your-image \
    --accelerator=type=nvidia-tesla-t4,count=1
```

Choose the option that best fits your budget, technical requirements, and usage patterns!