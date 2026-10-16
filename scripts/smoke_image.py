"""Exercise the built image, including ICMP, auth, health, and persistence."""
import argparse
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def eventually(check, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    raise AssertionError("Container check did not succeed before timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--host-network", action="store_true")
    args = parser.parse_args()
    name = "pingplotter-smoke-" + uuid.uuid4().hex[:10]
    volume = name + "-data"
    token = uuid.uuid4().hex
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    docker("volume", "create", volume)
    try:
        # Avoid bandwidth tests and external hosts: all probes stay on loopback.
        docker("run", "--rm", "-v", volume + ":/app/data", "--entrypoint", "python", args.image,
               "-c", "from pathlib import Path; Path('/app/data/settings.json').write_text('{\"speedtest_interval_minutes\":0,\"digest_interval_hours\":0}')")

        def start():
            port = 8000
            network = ["-p", "127.0.0.1::8000"]
            if args.host_network:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                network = ["--network", "host"]
            docker("run", "-d", "--name", name, "--cap-drop", "ALL", "--cap-add", "NET_RAW",
                   *network, "-v", volume + ":/app/data",
                   "-e", "PINGPLOTTER_PORT=" + str(port), "-e", "PINGPLOTTER_TOKEN=" + token, args.image)
            if not args.host_network:
                details = json.loads(docker("inspect", name))[0]
                port = int(details["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"])
            return "http://127.0.0.1:" + str(port)

        base = start()

        def request(path, payload=None, supplied_token=token):
            headers = {"Authorization": "Bearer " + supplied_token} if supplied_token else {}
            data = None
            if payload is not None:
                data = json.dumps(payload).encode()
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(base + path, data=data, headers=headers)
            with opener.open(req, timeout=5) as response:
                body = response.read()
                return json.loads(body) if path.startswith("/api/") else body

        eventually(lambda: request("/"))
        for supplied_token in ("", "wrong-token"):
            try:
                request("/api/health", supplied_token=supplied_token)
            except urllib.error.HTTPError as error:
                assert error.code == 401, error
            else:
                raise AssertionError("API accepted missing or incorrect token")
        assert request("/api/health")["status"] == "ok"
        device = request("/api/devices", {"name": "Loopback", "host": "127.0.0.1", "interval_sec": 1})
        results_path = f"/api/devices/{device['id']}/results"
        eventually(lambda: any(row["success"] and row["latency_ms"] is not None for row in request(results_path)))
        docker("exec", name, "traceroute", "-n", "-m", "1", "-w", "1", "127.0.0.1")
        eventually(lambda: json.loads(docker("inspect", name))[0]["State"]["Health"]["Status"] == "healthy")
        docker("stop", "--time", "10", name)
        docker("rm", name)
        base = start()
        eventually(lambda: request("/api/health")["devices"] == 1)
        assert request("/api/devices")[0]["name"] == "Loopback"
        assert any(row["success"] for row in request(results_path)), "Probe history was lost"
        print("PASS: HTTP, API auth, ICMP, traceroute, healthcheck, and persistent data")
    except BaseException:
        subprocess.run(["docker", "logs", name], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
