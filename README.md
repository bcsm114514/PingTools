# PingTools

- 英文
- [简体中文](./README_CN.md)

🎯 A concurrent IP/domain latency testing script supporting multiple protocols, formats, IPv4/IPv6, CIDR parsing, and result filtering/export.

## ✨ Features

- ✅ Supports UDP / TCP / Ping modes  
- 🌐 Supports IPv4 / IPv6 / Domain / CIDR parsing  
- 🚀 Multithreaded testing (default max 50 threads)  
- 📂 Export to CSV and JSON  
- 🎯 Port selection, min/max latency filtering, top-N output  
- 🧠 Auto deduplication and smart domain resolution  
- ⚠️ Optional IPv6 sample limiting to avoid large CIDR delays  
- 🖥️ Beautiful progress and result display in terminal  

## 🔧 Install Dependencies

```bash
pip install tqdm tabulate
```

> Recommended: Python 3.7+

## 📥 Input Format

Put targets in `ip.txt`, one per line, e.g.:

```
1.1.1.1
google.com
2408:XXX:XXX::/48
192.168.0.0/24
```

## 🚀 Usage

```bash
python ping.py --mode udp --port 443 --top 10 --output good.csv --failed bad.csv --json good.json --min 10 --max 200
```

### Parameters

| Argument | Description | Example |
|----------|-------------|---------|
| `--mode` | Test mode: `udp`, `tcp`, or `ping` | `--mode tcp` |
| `--port` | Port for `udp`/`tcp` | `--port 443` |
| `--top` | Show top N results | `--top 10` |
| `--output` | CSV output for successful results | `--output good.csv` |
| `--failed` | CSV output for failed results | `--failed failed.csv` |
| `--json` | JSON output | `--json result.json` |
| `--min` | Filter min latency (ms) | `--min 10` |
| `--max` | Filter max latency (ms) | `--max 200` |
| `--ipv6-limit` | Max IPv6 samples per CIDR (default 10, 0 = unlimited) | `--ipv6-limit 0` |
| `--verbose` | Show detailed info | `--verbose` |

## 📦 Output Example

Console output:

```
⏳ Running TCP test on 124 IPs...
📋 Top 10 IPs:
+---------------+--------------+----------+
|      IP       | Latency(ms)  |  Status  |
+---------------+--------------+----------+
| 1.1.1.1       |    18.56     | Success  |
| 8.8.8.8       |    24.01     | Success  |
```

## 🧠 Tips

- `ping` mode may vary by OS
- `UDP` is unreliable but fast for rough testing
- Limit IPv6 samples to avoid slow scans
- Supports comment lines, blank lines, and auto deduplication
- Useful for proxy node testing, CN2 filtering, etc.
