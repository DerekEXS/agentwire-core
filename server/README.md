# AgentWire Python A2A Service

基于 A2A v1.0.1 协议的服务端实现。

## 快速开始

```bash
pip install -r requirements.txt
python3 start.py --port 18800
```

## 端点

- `GET /.well-known/agent.json` - Agent Card
- `POST /a2a/jsonrpc` - JSON-RPC API
- `GET /health` - 健康检查
