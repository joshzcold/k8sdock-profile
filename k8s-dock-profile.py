#!/usr/bin/env python3
import sys
import threading
from argparse import ArgumentParser
from time import sleep
import subprocess
import traceback
import signal
import re
from os import system, name, environ, path
import json
con_dict = {}

def signal_handler(sig, frame):
    try:
        if not args.docker:
            for pod in con_dict:
                con_dict[pod]['cpu'] = 0
                con_dict[pod]['mem'] = 0
                for container in con_dict[pod]['containers']:
                    con_dict[pod]['cpu'] += con_dict[pod]['containers'][container]['cpu']
                    con_dict[pod]['mem'] += con_dict[pod]['containers'][container]['mem']
        else:
            for key, value in con_dict.items():
                value.pop('last_read_cpu', None)
        file = "kd-profile.json"
        if args.file:
            file = args.file
        print('\n writing to file ==> ', file)
        content = ""
        content = json.dumps(con_dict, indent = 4, sort_keys=True)
        print(content)
        with open(file, 'w') as outfile:
            json.dump(con_dict, outfile, indent=4, sort_keys=True)
    except:
        traceback.print_exc()
        sys.exit(1)
    sys.exit(0)

def parse_int(string):
    return int(re.sub(r'[^\d-]+', '', string))

def profile_docker():
    print("Profiling docker containers on local machine")
    list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
    if args.search:
        list_command += f"| grep {args.search}"
    print(list_command)
    normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
    containers = normal.communicate()[0].decode("utf-8")
    containers = [line for line in containers.split('\n') if line.strip() != '']
    print("Running off these containers => ", containers)
    if not containers:
        raise Exception(f"found no containers with {list_command}")
    for con in containers:
        if con:
            a = con.split()
            con_dict[a[1]] = {
                "id": a[0],
                "image": a[2],
                "last_read_cpu": [],
                "mhz": 0.0,
                "mb": 0.0
            }

    while True:
        for con_name, con_val in con_dict.items():
            try:
                paths = [line[0:].decode("utf-8") for line in subprocess.check_output(f"find /sys/fs/cgroup -iname {con_val['id']} || true", shell=True).splitlines()]
                paths_dct = {paths[i].split("/")[4]: paths[i] for i in range(0, len(paths))}

                cpu_file = open(paths_dct["cpu,cpuacct"] + "/cpuacct.usage_percpu")
                cpu_stats = cpu_file.read()
                cpu_file.close()

                ram_file = open(paths_dct["memory"] + "/memory.max_usage_in_bytes")
                ram_stats = float(ram_file.read())
                ram_file.close()
                # Megabytes = Bytes ÷ 1,048,576
                ram_mb = ram_stats/1048576
                # RAM Operation
                if ram_mb > float(con_val["mb"]):
                    print(f"{con_name} RAM ==> {ram_mb}mb")
                    con_dict[con_name]["mb"] = ram_mb

                # CPU Operation
                core_stats = cpu_stats.split()
                if not con_val["last_read_cpu"]:
                    con_val["last_read_cpu"] = core_stats
                    continue
                else:
                    # subtract last read value from new value
                    result = 0
                    for i in range(len(core_stats)):
                        result += (int(core_stats[i]) - int(con_val["last_read_cpu"][i]))
                    result = result / 1000000  # hz => mhz = hz/1 mil
                    if result > float(con_dict[con_name]["mhz"]):
                        print(f"{con_name} CPU ==> {result}mhz")
                        con_dict[con_name]["mhz"] = result
                    con_val["last_read_cpu"] = core_stats
            except FileNotFoundError:
                # Replace a container in con_dict based on container name if its restarted,killed
                # and its container id has changed.
                print("cgroup file not found, container restart or killed. Attempting to replace and continue ==> ", con_name)
                list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
                normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
                containers = normal.communicate()[0].decode("utf-8").split("\n")
                for con in containers:
                    if con:
                        a = con.split()
                        if con_name is a[1]:
                            con_dict[a[1]]["id"] = a[0]
            except KeyError:
                print(f"Key Error Attempting to replace: Container Name:{con_name} Container Data:{con_val} Container Paths:{paths_dct}")
                list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
                normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
                containers = normal.communicate()[0].decode("utf-8").split("\n")
                for con in containers:
                    if con:
                        a = con.split()
                        if con_name is a[1]:
                            con_dict[a[1]]["id"] = a[0]
            except Exception as err:
                print(f"Exception! something went wrong but im continuing {err}")

def profile_k8s():
    if args.label_selectors:
        query = f" -l {args.label_selectors}"
    else:
        query = ""
    command = f"kubectl top pods --no-headers --containers -n {args.namespace or 'default'}{query}"
    if args.search:
        command += f"| grep {args.search}"
    print(command)
    while True:
        normal = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        stats = normal.communicate()[0].decode("utf-8")
        pod_list = stats.split("\n")
        for pod in pod_list:
            if pod:  # pod is not empty
                i = pod.split()
                if args.namespace:
                    namespace, pod, container, cpu, mem = args.namespace,i[0],i[1],parse_int(i[2]),parse_int(i[3])
                else:
                    namespace, pod, container, cpu, mem = i[0],i[1],i[2],parse_int(i[3]),parse_int(i[4])
                if pod not in con_dict:
                    con_dict[pod] = {
                        "namespace": namespace,
                        "containers":{}
                    }
                if container not in con_dict[pod]['containers']:
                    con_dict[pod]['containers'][container] = {
                        "cpu": cpu,
                        "mem": mem
                    }
                else:
                    if con_dict[pod]['containers'][container]["cpu"] < cpu:
                        con_dict[pod]['containers'][container]["cpu"] = cpu
                    if con_dict[pod]['containers'][container]["mem"] < mem:
                        con_dict[pod]['containers'][container]["mem"] = mem
        if not args.quiet:
            print(json.dumps(con_dict, indent=4))

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-n", "--namespace", help="choose k8s namespace")
    parser.add_argument("-d", "--docker", help="just profile docker containers", action="store_true")
    parser.add_argument("-f", "--file", help="choose file to output to")
    parser.add_argument("-s", "--search", help="fuzzy match search term using grep")
    parser.add_argument("-l", "--label-selectors", help="k8s selector query ex: key1=value1,key2=value2")
    parser.add_argument("-t", "--timeout", help="time in seconds to run the script and exit. Default is to run forever.")
    parser.add_argument("-q", "--quiet", help="quiet mode", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    print("Press Ctrl + C to stop and write results to file")
    print("------------------------------------------------")
    # TODO We need to fix the OS path is file
    if not environ.get("KUBECONFIG") and not path.isfile("~/.kube/config"):
        raise Exception("KUBECONFIG env var and ~/.kube/config not set")
    if args.timeout:
        if args.docker:
            p = threading.Thread(target=profile_docker, args=())
        else:
            p = threading.Thread(target=profile_k8s, args=())
        p.daemon = True
        p.start()
        sleep(int(args.timeout))
        print("Hit timeout finishing up... ")
        signal_handler("","")
    else:
        if args.docker:
            profile_docker()
        else:
            profile_k8s()
