# coin-go

Go 语言重写版 coin 插件服务，与 Python 版 `coin.py` API 完全兼容，并发性能更高。

## 功能

- HTTP 代理转发 (`/api/proxy`)
- Lighter 交易 (`/api/proxy/lighter/init`, `/api/proxy/lighter/order`)
- WebSocket 连接管理 (`/api/ws/*`)
- 代理控制面板 (`/`)

## 快速启动（Docker，推荐）

无需本地 Python 和代理，容器内默认直连网络：

```bash
docker run -d --name coin-go \
  -p 50888:50888 \
  --restart unless-stopped \
  testcp98/coin-go:latest
```

或使用 docker-compose：

```bash
cd coin-go
docker compose up -d
```

访问 http://localhost:50888 查看控制面板。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `50888` | 服务端口 |
| 无 | - | 本镜像已移除本地 HTTP PROXY 功能，默认始终直连网络。 |

## 本地编译

```bash
cd coin-go
GOTOOLCHAIN=go1.23.0 go build -o coin-go .
./coin-go
```

## 构建并推送镜像

```bash
# 交叉编译 Linux 二进制
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o coin-go-linux .
cp /etc/ssl/cert.pem ca-certificates.crt

# 构建镜像（无需拉取基础镜像）
docker build -f Dockerfile.scratch -t testcp98/coin-go:latest .

# 推送（需先 docker login）
docker push testcp98/coin-go:latest
```

## 与 Python 版的差异

- Docker 模式默认 **关闭** 本地代理，出站请求直连（适合服务器部署）
- 使用 Go 原生 goroutine 处理 WebSocket 和 HTTP，并发能力更强
- 使用 [lighter-go](https://github.com/0xJord4n/lighter-go) SDK 替代 Python lighter 库
