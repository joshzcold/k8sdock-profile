import sys
from argparse import ArgumentParser
from time import sleep
import subprocess
import signal
import re
import os
stat_map = {}
con_map = {}


def signal_handler(sig, frame):
    # if args.file write to that file instead of the default
    if args.file:
        print('\n writing to file ==> ', args.file)
        f = open(args.file)
        content = ""
        if args.docker:
            for key, value in con_map.items():
                # Consistent Tabbing between rows. look into print.format()
                # Maybe some colors???
                print(f"{key} ==> {value}")
                content += f"docker container: {key} {0: <16} max cpu: {value['mhz']}mhz max ram {value['mb']}mb image: {value['image']}  id: {value['id']}\n"
        else:
            for key, value in stat_map.items():
                print(f"{key} ==> {value}")
                content += f"k8s pod name: {key} {0: <16} cpu: {value['cpu']}mhz mem: {value['mem']}Mi \n"
        content.format()
        f.write(content)
        f.close()

    else:
        file = f"k8s-dock.profile"
        print('\n writing to file ==> ', file)
        f = open(file, "w")
        content = ""
        if args.docker:
            for key, value in con_map.items():
                # Consistent Tabbing between rows. look into print.format()
                # Maybe some colors??? 
                print(f"{key} ==> {value}")
                content += f"docker container: {key} {0: <16} max cpu: {value['mhz']}mhz max ram {value['mb']}mb image: {value['image']}  id: {value['id']}\n"
        else:
            for key, value in stat_map.items():
                print(f"{key} ==> {value}")
                content += f"k8s pod name: {key} {0: <16} cpu: {value['cpu']}mhz mem: {value['mem']}Mi \n"
        content.format()
        f.write(content)
        f.close()
    sys.exit(0)


def parse_int(string):
    return int(re.sub(r'[^\d-]+', '', string))


def profile_docker():
    print("Profiling docker containers on local machine")
    list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
    normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
    containers = normal.communicate()[0].decode("utf-8")
    containers = [line for line in containers.split('\n') if line.strip() != '']
    print("Running off these containers => ", containers)
    if not containers:
        raise Exception(f"found no containers with {list_command}")
    for con in containers:
        if con:
            a = con.split()
            con_map[a[1]] = {
                "id": a[0],
                "image": a[2],
                "last_read_cpu": [],
                "mhz": 0.0,
                "mb": 0.0
            }

    while True:
        for con_name, con_val in con_map.items():
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
                    con_map[con_name]["mb"] = ram_mb

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
                    if result > float(con_map[con_name]["mhz"]):
                        print(f"{con_name} CPU ==> {result}mhz")
                        con_map[con_name]["mhz"] = result
                    con_val["last_read_cpu"] = core_stats
            except FileNotFoundError:
                # Replace a container in con_map based on container name if its restarted,killed
                # and its container id has changed.
                print("cgroup file not found, container restart or killed. Attempting to replace and continue ==> ", con_name)
                list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
                normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
                containers = normal.communicate()[0].decode("utf-8").split("\n")
                for con in containers:
                    if con:
                        a = con.split()
                        if con_name is a[1]:
                            con_map[a[1]]["id"] = a[0]
            except KeyError:
                print(f"Key Error Attempting to replace: Container Name:{con_name} Container Data:{con_val} Container Paths:{paths_dct}")
                list_command = 'docker container ls --no-trunc --format "{{.ID}} {{.Names}} {{.Image}}"'
                normal = subprocess.Popen(list_command, stdout=subprocess.PIPE, shell=True)
                containers = normal.communicate()[0].decode("utf-8").split("\n")
                for con in containers:
                    if con:
                        a = con.split()
                        if con_name is a[1]:
                            con_map[a[1]]["id"] = a[0]
            except Exception as err:
                print(f"Exception! something went wrong but im continuing {err}")


def profile_k8s():
    if args.namespace:
        namespace_arg = f"-n ${args.namespace}"
        print(f"Profiling kubernetes pods in {args.namespace} namespace")
        command = f"kubectl top pods {namespace_arg} | sed 1d "
    else:
        print("Profiling kubernetes pods in default namespace")
        command = "kubectl top pods -n default | sed 1d "

    while True:
        normal = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        stats = normal.communicate()[0].decode("utf-8")
        print(stats)
        pod_list = stats.split("\n")
        for pod in pod_list:
            if pod:  # pod is not empty
                i = pod.split()
                if i[0] not in stat_map:
                    stat_map[f"{i[0]}"] = {
                        "cpu": parse_int(i[1]),
                        "mem": parse_int(i[2])
                    }
                else:
                    if stat_map[f"{i[0]}"]["cpu"] < parse_int(i[1]):
                        stat_map[f"{i[0]}"]["cpu"] = parse_int(i[1])
                    if stat_map[f"{i[0]}"]["mem"] < parse_int(i[2]):
                        stat_map[f"{i[0]}"]["mem"] = parse_int(i[2])
        print(stat_map)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    print("Press Ctrl + C to stop and write results to file")
    sleep(2)
    parser = ArgumentParser()
    parser.add_argument("-d", "--docker", help="profile docker containers", action="store_true")
    parser.add_argument("-k", "--kubernetes", help="profile k8s pods containers", action="store_true")
    parser.add_argument("-n", "--namespace", help="choose k8s namespace")
    parser.add_argument("-f", "--file", help="choose file to output to")
    args = parser.parse_args()
    if args.docker:
        profile_docker()
    if args.kubernetes:
        # We need to fix the OS path is file
        if not os.environ.get("KUBECONFIG") and not os.path.isfile("~/.kube/config"):
            raise Exception("KUBECONFIG env var and ~/.kube/config not set")
        profile_k8s()
