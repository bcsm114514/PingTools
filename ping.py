import socket
import time
import csv
import ipaddress
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from tabulate import tabulate

# 配置参数
TIMEOUT_SECONDS = 1.5
TIMEOUT_THRESHOLD_MS = TIMEOUT_SECONDS * 1000 - 10
MAX_WORKERS = 50  # 减少线程数以优化性能
DNS_TIMEOUT = 2   # DNS解析超时

def test_udp_latency(ip, port):
    try:
        ip_obj = ipaddress.ip_address(ip)
        family = socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(TIMEOUT_SECONDS)
        start_time = time.time()
        sock.sendto(b'', (ip, port))
        try:
            sock.recvfrom(1024)
        except socket.timeout:
            pass
        latency = (time.time() - start_time) * 1000
        sock.close()
        if latency >= TIMEOUT_THRESHOLD_MS:
            return (f"{ip}:{port}", round(latency, 2), "Timeout")
        return (f"{ip}:{port}", round(latency, 2), "Success")
    except Exception as e:
        return (f"{ip}:{port}", None, f"Error: {e}")

def test_tcp_latency(ip, port):
    try:
        ip_obj = ipaddress.ip_address(ip)
        family = socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_SECONDS)
        start_time = time.time()
        sock.connect((ip, port))
        latency = (time.time() - start_time) * 1000
        sock.close()
        return (f"{ip}:{port}", round(latency, 2), "Success")
    except socket.timeout:
        return (f"{ip}:{port}", None, "Timeout")
    except Exception as e:
        return (f"{ip}:{port}", None, f"Error: {e}")

def test_ping_latency(ip):
    try:
        # 简单ICMP ping实现
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(TIMEOUT_SECONDS)
        sock.sendto(b'', (ip, 1))
        try:
            sock.recvfrom(1024)
        except socket.timeout:
            pass
        latency = (time.time() - start_time) * 1000
        sock.close()
        if latency >= TIMEOUT_THRESHOLD_MS:
            return (ip, round(latency, 2), "Timeout")
        return (ip, round(latency, 2), "Success")
    except Exception as e:
        return (ip, None, f"Error: {e}")

def run_test(ip, mode, port=None, verbose=False):
    if verbose:
        print(f"[正在测试] {ip}:{port} ...")
    if mode == "udp":
        return test_udp_latency(ip, port)
    elif mode == "tcp":
        return test_tcp_latency(ip, port)
    elif mode == "ping":
        return test_ping_latency(ip)
    else:
        return (ip, None, "Unknown mode")

def resolve_domain(domain, default_port):
    """带超时的域名解析"""
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT)
        infos = socket.getaddrinfo(domain, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return [(info[4][0], default_port) for info in infos]
    except (socket.gaierror, socket.timeout):
        return []

def parse_targets(lines, ipv6_sample_limit=10, default_port=443):
    targets = set()
    ipv6_port_pattern = re.compile(r'^$$([0-9a-fA-F:]+)$$(?::(\d+))?$')
    
    for line in tqdm(lines, desc="解析IP/域名", unit="行"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        try:
            # 1. IPv6带端口格式 [2408::1]:443
            match = ipv6_port_pattern.match(line)
            if match:
                ip = match.group(1)
                port = int(match.group(2)) if match.group(2) else default_port
                targets.add((ip, port))
                continue

            # 2. CIDR网络
            if "/" in line:
                net = ipaddress.ip_network(line, strict=False)
                if net.version == 6:
                    sampled_hosts = net.hosts() if ipv6_sample_limit == 0 else list(net.hosts())[:ipv6_sample_limit]
                else:
                    sampled_hosts = net.hosts()
                for ip in sampled_hosts:
                    targets.add((str(ip), default_port))
                continue

            # 3. IPv4/IPv6带端口 1.1.1.1:8443
            if ":" in line and line.count(":") == 1:  # 简单判断IPv4
                ip, port = line.split(":")
                port = int(port)
                targets.add((ip, port))
                continue

            # 4. 纯IP地址
            try:
                ipaddress.ip_address(line)
                targets.add((line, default_port))
                continue
            except ValueError:
                pass

            # 5. 域名解析
            resolved = resolve_domain(line, default_port)
            for ip, port in resolved:
                targets.add((ip, port))

        except Exception as e:
            print(f"⚠️ 解析失败: {line}, 错误: {e}")
    return list(targets)

def write_csv(filename, data, headers):
    with open(filename, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(data)

def write_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([{"ip:port": d[0], "latency": d[1], "status": d[2]} for d in data], 
                 f, indent=2, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="高效IP延迟测试工具")
    parser.add_argument('--mode', choices=['udp', 'tcp', 'ping'], required=True, help='测试模式: udp/tcp/ping')
    parser.add_argument('--port', type=int, default=443, help='端口号(udp/tcp模式使用)')
    parser.add_argument('--top', type=int, default=10, help='输出前N个低延迟IP')
    parser.add_argument('--output', type=str, default="result.csv", help='成功结果文件')
    parser.add_argument('--failed', type=str, default="failed.csv", help='失败结果文件')
    parser.add_argument('--json', type=str, help='JSON输出文件')
    parser.add_argument('--min', type=float, help='最低延迟(ms)')
    parser.add_argument('--max', type=float, help='最高延迟(ms)')
    parser.add_argument('--verbose', action='store_true', help='显示详细进度')
    parser.add_argument('--ipv6-limit', type=int, default=10, help='IPv6段采样数量(0表示全部)')
    args = parser.parse_args()

    try:
        with open("ip.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            raw_ips = parse_targets(lines, ipv6_sample_limit=args.ipv6_limit)
    except FileNotFoundError:
        print("❌ 找不到ip.txt文件")
        return

    print(f"⏳ 开始{args.mode.upper()}测试，共{len(raw_ips)}个IP...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(run_test, ip, args.mode, port, args.verbose): (ip, port)
            for ip, port in raw_ips
        }
        
        for future in tqdm(as_completed(futures), total=len(futures), desc="测试进度"):
            results.append(future.result())

    # 结果处理
    success_results = [
        r for r in results if r[2] == "Success"
        and (args.min is None or (r[1] is not None and r[1] >= args.min))
        and (args.max is None or (r[1] is not None and r[1] <= args.max))
    ]
    success_results = sorted(success_results, key=lambda x: x[1])[:args.top]
    failed_results = [r for r in results if r[2] != "Success"]

    # 写入文件
    write_csv(args.output, success_results, ["IP:Port", "Latency(ms)", "Status"])
    write_csv(args.failed, failed_results, ["IP:Port", "Latency(ms)", "Status"])
    
    if args.json:
        write_json(args.json, success_results)

    # 显示结果
    print("\n📋 前{}个低延迟IP：".format(len(success_results)))
    print(tabulate(success_results, headers=["IP:Port", "Latency(ms)", "Status"], tablefmt="pretty"))
    print(f"\n✅ 测试完成，结果已保存至: {args.output}(成功) 和 {args.failed}(失败)")
    if args.json:
        print(f"📄 JSON格式输出: {args.json}")

if __name__ == "__main__":
    main()
