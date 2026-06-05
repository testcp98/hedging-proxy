# Build stage (multi-stage, needs network)
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache git ca-certificates

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /coin-go .

# Runtime stage — scratch 镜像更小，无需基础镜像
FROM scratch

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder --chmod=755 /coin-go /coin-go

ENV PORT=50888
ENV PROXY_ENABLED=false
ENV PROXY_HOST=host.docker.internal

EXPOSE 50888

ENTRYPOINT ["/coin-go"]
