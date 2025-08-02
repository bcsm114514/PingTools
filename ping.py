import socket
import time
import csv
import ipaddress
import subprocess
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from tabulate import tabulate

TIMEOUT_SECONDS = 3
TIMEOUT_THRESHOLD_MS = TIMEOUT_SECONDS * 1000 - 10

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
            return (ip, round(latency, 2), "Timeout")
        else:
            return (ip, round(latency, 2), "Success")
    except Exception as e:
        return (ip, None, f"Error: {e}")

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
        return (ip, round(latency, 2), "Success")
    except socket.timeout:
        return (ip, None, "Timeout")
    except Exception as e:
        return (ip, None, f"Error: {e}")

def test_ping_latency(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        cmd = ["ping", "-n", "1", ip] if ip_obj.version == 4 else ["ping", "-n", "1", ip, "-6"]
        start_time = time.time()
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS)
        latency = (time.time() - start_time) * 1000
        if result.returncode == 0:
            return (ip, round(latency, 2), "Success")
        else:
            return (ip, None, "Ping failed")
    except subprocess.TimeoutExpired:
        return (ip, None, "Timeout")
    except Exception as e:
        return (ip, None, f"Error: {e}")

def run_test(ip, mode, port=None, verbose=False):
    if verbose:
        print(f"[正在测试] {ip} ...")
    if mode == "udp":
        return test_udp_latency(ip, port)
    elif mode == "tcp":
        return test_tcp_latency(ip, port)
    elif mode == "ping":
        return test_ping_latency(ip)
    else:
        return (ip, None, "Unknown mode")

    if verbose:
        latency_display = f"{result[1]} ms" if result[1] is not None else "N/A"
        print(f"[结果] {ip} - {latency_display} - {result[2]}")
    return result

def write_csv(filename, data, headers):
    with open(filename, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(data)

def write_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([{"ip": d[0], "latency": d[1], "status": d[2]} for d in data],f, indent=2, ensure_ascii=False)

def parse_targets(lines, ipv6_sample_limit=10):
    targets = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if "/" in line:
                net = ipaddress.ip_network(line, strict=False)
                if net.version == 6:
                    # 限制 IPv6 采样数量
                    if ipv6_sample_limit == 0:
                        sampled_hosts = net.hosts()
                    else:
                        sampled_hosts = (h for i, h in enumerate(net.hosts()) if i < ipv6_sample_limit)
                    targets.update(map(str, sampled_hosts))
                else:
                    targets.update(map(str, net.hosts()))
            else:
                # 域名或单个IP
                try:
                    ipaddress.ip_address(line)  # 如果是 IP，不处理
                    targets.add(line)
                except ValueError:
                    # 是域名，解析为多个IP（IPv4 + IPv6）
                    for family in (socket.AF_INET, socket.AF_INET6):
                        try:
                            infos = socket.getaddrinfo(line, None, family, socket.SOCK_STREAM)
                            for info in infos:
                                ip = info[4][0]
                                targets.add(ip)
                        except socket.gaierror:
                            continue
        except Exception as e:
            print(f"⚠️ 无法解析：{line}，错误：{e}")
    return list(targets)  # 自动去重后返回

def main():
    parser = argparse.ArgumentParser(description="高级 IP 延迟测试工具")
    parser.add_argument('--mode', choices=['udp', 'tcp', 'ping'], required=True, help='测试模式: udp / tcp / ping')
    parser.add_argument('--port', type=int, default=443, help='端口号（用于 udp / tcp）')
    parser.add_argument('--top', type=int, default=10, help='输出前N个成功IP')
    parser.add_argument('--output', type=str, default="result.csv", help='成功输出文件名')
    parser.add_argument('--failed', type=str, default="failed.csv", help='失败输出文件名')
    parser.add_argument('--json', type=str, help='是否额外输出 JSON 文件名')
    parser.add_argument('--min', type=float, help='最小延迟过滤(ms)')
    parser.add_argument('--max', type=float, help='最大延迟过滤(ms)')
    parser.add_argument('--verbose', action='store_true', help='是否打印详细测试进度')
    parser.add_argument('--ipv6-limit', type=int, default=10, help='每个 IPv6 段采样数量（默认10，0表示全量）')
    args = parser.parse_args()

    try:
        with open("ip.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            raw_ips = parse_targets(lines, ipv6_sample_limit=args.ipv6_limit)
    except FileNotFoundError:
        print("❌ ip.txt 文件不存在")
        return

    results = []
    print(f"⏳ 正在进行 {args.mode.upper()} 测试，共 {len(raw_ips)} 个 IP...")

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {
            executor.submit(run_test, ip, args.mode, args.port, args.verbose): ip
            for ip in raw_ips
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="测试进度"):
            results.append(future.result())

    success_results = [
        r for r in results if r[2] == "Success"
        and (args.min is None or r[1] >= args.min)
        and (args.max is None or r[1] <= args.max)
    ]
    success_results = sorted(success_results, key=lambda x: x[1])[:args.top]
    failed_results = [r for r in results if r[2] != "Success"]

    write_csv(args.output, success_results, ["IP", "Latency(ms)", "Status"])
    write_csv(args.failed, failed_results, ["IP", "Latency(ms)", "Status"])
    if args.json:
        write_json(args.json, success_results)

    print("\n📋 前 {} 个成功 IP：".format(len(success_results)))
    print(tabulate(success_results, headers=["IP", "Latency(ms)", "Status"], tablefmt="pretty"))
    print(f"\n✅ 测试完成，结果保存至：{args.output}（成功）和 {args.failed}（失败）")
    if args.json:
        print(f"📄 JSON 格式输出：{args.json}")

if __name__ == "__main__":
    main()
